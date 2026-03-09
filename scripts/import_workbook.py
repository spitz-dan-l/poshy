from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOCREL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKGREL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "pkgrel": PKGREL_NS}

POTION_SHEETS = ("PotionsDC&B", "PotionsA&X")
INGREDIENT_SHEET = "Ingrediants"
ACCESSORIES_SHEET = "Accessories"
EQUIPMENT_SHEETS = (
    "Axes&Spears",
    "Swords&Bows",
    "Staves&Orbs",
    "Runestones",
    "Light&Heavy ",
    "Robe&Hide",
    "Golem&Gauntlet",
    "Headware",
    "Familiars",
    "Footwear",
    "Mounts&Legs",
    ACCESSORIES_SHEET,
)
PRICE_RE = re.compile(r"^\s*(\d+)\s*(?:G|Gold)\b.*$", re.IGNORECASE)
INGREDIENT_RE = re.compile(r"^(.*?)\s*\((\d+)\)$")
RANK_RE = re.compile(r"^\s*([A-Z])(?:\s|$)")
PIECE_SUFFIX_MARKER_RE = re.compile(r"^(.*?\bpiece)\s+[A-Z]$", re.IGNORECASE)
CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")
ACCESSORY_GEM_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

POTION_SUBTYPE_RULES = (
    ("brew", re.compile(r"^brew of ", re.IGNORECASE)),
    ("elixir", re.compile(r"^elixir of ", re.IGNORECASE)),
    ("medicine", re.compile(r" medicine$", re.IGNORECASE)),
    ("potion", re.compile(r" potion$", re.IGNORECASE)),
    ("grenade", re.compile(r" grenade$", re.IGNORECASE)),
    ("toxin", re.compile(r" toxin$", re.IGNORECASE)),
    ("solution", re.compile(r" solution$", re.IGNORECASE)),
)

POTION_SUBTYPE_LABELS = {
    "medicine": "Medicine",
    "elixir": "Elixir",
    "potion": "Potion",
    "toxin": "Toxin",
    "solution": "Solution",
    "grenade": "Grenade",
    "brew": "Brew",
}

VALID_TIERS = {"A", "B", "C", "D", "X"}
VALID_EQUIPMENT_CATEGORIES = {"equipment", "accessory"}


class ImportErrorWithContext(RuntimeError):
    pass


def collapse_space(value: str) -> str:
    return " ".join(str(value).strip().split())


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def column_to_index(column: str) -> int:
    value = 0
    for char in column:
        value = (value * 26) + (ord(char.upper()) - ord("A") + 1)
    return value


def index_to_column(index: int) -> str:
    letters: list[str] = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def iter_columns(start: str, end: str) -> list[str]:
    start_index = column_to_index(start)
    end_index = column_to_index(end)
    return [index_to_column(index) for index in range(start_index, end_index + 1)]


def extract_price(raw_value: str, context: str) -> int:
    match = PRICE_RE.fullmatch(collapse_space(raw_value))
    if match is None:
        raise ImportErrorWithContext(f"{context} does not contain a price marker: {raw_value!r}")
    return int(match.group(1))


def maybe_extract_price(raw_value: str) -> int | None:
    match = PRICE_RE.fullmatch(collapse_space(raw_value))
    return None if match is None else int(match.group(1))


def normalize_stat_key(label: str) -> str:
    collapsed = collapse_space(label).lower()
    key = NON_ALNUM_RE.sub("_", collapsed).strip("_")
    return key


def normalize_effects(values: list[str]) -> list[str]:
    return [value for value in (collapse_space(item) for item in values) if value]


def build_stats(
    row: dict[str, str],
    header_row: dict[str, str],
    stat_columns: tuple[str, ...],
    context: str,
) -> dict[str, str]:
    stats: dict[str, str] = {}
    for column in stat_columns:
        header = collapse_space(header_row.get(column, ""))
        key = normalize_stat_key(header)
        if not key:
            raise ImportErrorWithContext(f"{context} is missing a stat header for column {column}")
        value = collapse_space(row.get(column, ""))
        if value:
            stats[key] = value
    return stats


def collect_block_effects(
    row: dict[str, str],
    start_column: str,
    end_column: str,
    excluded_columns: set[str],
) -> list[str]:
    values = [
        collapse_space(row.get(column, ""))
        for column in iter_columns(start_column, end_column)
        if column not in excluded_columns
    ]
    return normalize_effects(values)


def parse_max_hp(raw_value: str, context: str, *, allow_null_markers: bool = False) -> int | None:
    value = collapse_space(raw_value)
    if not value:
        raise ImportErrorWithContext(f"{context} is missing HP")
    if allow_null_markers and value.casefold() in {"n/a", "na"}:
        return None
    if not value.isdigit():
        raise ImportErrorWithContext(f"{context} has an invalid HP value: {raw_value!r}")
    return int(value)


def infer_equipment_category(family: str, source_sheet: str) -> str:
    if source_sheet.strip() != ACCESSORIES_SHEET:
        return "equipment"
    return "accessory" if family in {"ring", "necklace", "talisman"} else "equipment"


def build_equipment_definition(
    *,
    name: str,
    family: str,
    category: str,
    rank: str,
    buy_price: int,
    max_hp: int | None,
    stats: dict[str, str],
    effects: list[str],
    socket_policy: dict[str, int] | None = None,
) -> dict[str, object]:
    definition: dict[str, object] = {
        "name": collapse_space(name),
        "family": family,
        "category": category,
        "rank": normalize_tier(rank) if collapse_space(rank) else "",
        "buy_price": buy_price,
        "max_hp": max_hp,
        "stats": stats,
        "effects": normalize_effects(effects),
    }
    if socket_policy is not None:
        definition["socket_policy"] = socket_policy
    return definition


def build_alias_map(raw_aliases: dict[str, str], label: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw_name, target_name in (raw_aliases or {}).items():
        key = collapse_space(raw_name).casefold()
        target = collapse_space(target_name)
        if not key:
            raise ImportErrorWithContext(f"{label} alias contains a blank key")
        if not target:
            raise ImportErrorWithContext(f"{label} alias for {raw_name!r} maps to a blank target")
        previous = mapping.get(key)
        if previous is not None and previous != target:
            raise ImportErrorWithContext(
                f"{label} alias collision for {raw_name!r}: {previous!r} vs {target!r}"
            )
        mapping[key] = target
    return mapping


def apply_alias(raw_name: str, aliases: dict[str, str]) -> str:
    name = collapse_space(raw_name)
    return aliases.get(name.casefold(), name)


def canonicalize_known_name(raw_name: str, aliases: dict[str, str], known_names: dict[str, str]) -> str:
    name = apply_alias(raw_name, aliases)
    return known_names.get(name.casefold(), name)


def parse_inline_string(cell: ET.Element) -> str:
    return "".join(text.text or "" for text in cell.iterfind(".//main:t", NS))


def read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return parse_inline_string(cell)
    value = cell.find("main:v", NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        return shared_strings[int(value.text)]
    return value.text


def read_workbook(path: Path) -> dict[str, list[dict[str, str]]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in rels.findall("pkgrel:Relationship", NS)
        }

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared.findall("main:si", NS):
                shared_strings.append("".join(text.text or "" for text in item.iterfind(".//main:t", NS)))

        sheet_targets: dict[str, str] = {}
        for sheet in workbook.findall("main:sheets/main:sheet", NS):
            rel_id = sheet.attrib[f"{{{DOCREL_NS}}}id"]
            target = rel_map[rel_id]
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            sheet_targets[sheet.attrib["name"]] = target

        rows_by_sheet: dict[str, list[dict[str, str]]] = {}
        for sheet_name, target in sheet_targets.items():
            root = ET.fromstring(archive.read(target))
            rows: list[dict[str, str]] = []
            for row in root.findall("main:sheetData/main:row", NS):
                cells = {"_row": row.attrib["r"]}
                for cell in row.findall("main:c", NS):
                    match = CELL_REF_RE.match(cell.attrib.get("r", ""))
                    if not match:
                        continue
                    cells[match.group(1)] = read_cell_value(cell, shared_strings)
                rows.append(cells)
            rows_by_sheet[sheet_name] = rows
        return rows_by_sheet


def infer_potion_subtype(name: str) -> str:
    for subtype, pattern in POTION_SUBTYPE_RULES:
        if pattern.search(name):
            return subtype
    raise ImportErrorWithContext(f"Unable to infer potion subtype from name: {name}")


def normalize_tier(raw_value: str) -> str:
    match = RANK_RE.match(raw_value or "")
    if match is None:
        raise ImportErrorWithContext(f"Unable to parse tier from rank value: {raw_value!r}")
    tier = match.group(1).upper()
    if tier not in VALID_TIERS:
        raise ImportErrorWithContext(f"Unsupported tier {tier!r} from rank value {raw_value!r}")
    return tier


def parse_ingredient_cell(raw_value: str) -> tuple[str, int] | None:
    text = collapse_space(raw_value)
    if not text:
        return None
    match = INGREDIENT_RE.fullmatch(text)
    if match is None:
        return None
    return collapse_space(match.group(1)), int(match.group(2))


def normalize_counter_keys(
    raw_counter: dict[str, int],
    aliases: dict[str, str],
    known_names: dict[str, str],
    label: str,
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for raw_name, raw_count in (raw_counter or {}).items():
        count = int(raw_count)
        if count < 0:
            raise ImportErrorWithContext(f"{label} contains a negative count for {raw_name!r}")
        canonical = canonicalize_known_name(raw_name, aliases, known_names)
        if canonical.casefold() not in known_names:
            raise ImportErrorWithContext(f"{label} references unknown name {raw_name!r}")
        counter[known_names[canonical.casefold()]] += count
    return dict(sorted(counter.items(), key=lambda item: item[0].casefold()))


def normalize_flag_keys(
    raw_map: dict[str, bool],
    aliases: dict[str, str],
    known_names: dict[str, str],
    label: str,
) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for raw_name, enabled in (raw_map or {}).items():
        if not enabled:
            continue
        canonical = canonicalize_known_name(raw_name, aliases, known_names)
        if canonical.casefold() not in known_names:
            raise ImportErrorWithContext(f"{label} references unknown name {raw_name!r}")
        flags[known_names[canonical.casefold()]] = True
    return dict(sorted(flags.items(), key=lambda item: item[0].casefold()))


def parse_standard_equipment_block(
    rows: list[dict[str, str]],
    sheet_name: str,
    spec: dict[str, object],
) -> list[dict[str, object]]:
    header_row = rows[0]
    current_price: int | None = None
    family_headers: dict[str, str] = spec.get("family_headers", {})
    active_family = family_headers.get(collapse_space(header_row.get(spec["name_col"], "")).casefold(), spec.get("family"))
    item_family_override = spec.get("item_family_override")
    definitions: list[dict[str, object]] = []
    for row in rows[1:]:
        raw_name = collapse_space(row.get(spec["name_col"], ""))
        rank = collapse_space(row.get(spec["rank_col"], ""))
        if raw_name:
            header_family = family_headers.get(raw_name.casefold())
            if header_family is not None and (not rank or rank.casefold() == "rank"):
                active_family = header_family
                current_price = None
                continue
        if raw_name:
            price = maybe_extract_price(raw_name)
            if price is not None:
                current_price = price
                continue
        if current_price is None or not raw_name or active_family is None:
            continue
        if not rank or RANK_RE.match(rank) is None:
            continue
        family = active_family
        if callable(item_family_override):
            family = item_family_override(raw_name, active_family)
        context = f'{sheet_name.strip()} "{raw_name}"'
        max_hp = parse_max_hp(
            row.get(spec["hp_col"], ""),
            f"{context} HP",
            allow_null_markers=bool(spec.get("allow_null_hp")),
        )
        excluded = {spec["name_col"], spec["rank_col"], spec["hp_col"], *spec["stat_cols"]}
        definitions.append(
            build_equipment_definition(
                name=raw_name,
                family=family,
                category=infer_equipment_category(family, sheet_name),
                rank=rank,
                buy_price=current_price,
                max_hp=max_hp,
                stats=build_stats(row, header_row, spec["stat_cols"], context),
                effects=collect_block_effects(row, spec["name_col"], spec["block_end_col"], excluded),
            )
        )
    return definitions


def parse_familiars_sheet(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    header_row = rows[0]
    block_specs = (
        {
            "family": "familiar",
            "name_col": "A",
            "rank_col": "B",
            "hp_col": "C",
            "stat_cols": ("D", "E", "F", "G", "H", "I", "J", "K", "L", "M"),
            "block_end_col": "N",
        },
        {
            "family": "familiar",
            "name_col": "O",
            "rank_col": "P",
            "hp_col": "Q",
            "stat_cols": ("R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA"),
            "block_end_col": "AE",
        },
    )
    current_prices = {spec["name_col"]: None for spec in block_specs}
    active_definitions: dict[str, dict[str, object] | None] = {spec["name_col"]: None for spec in block_specs}
    definitions: list[dict[str, object]] = []

    for row in rows[1:]:
        for spec in block_specs:
            name_col = spec["name_col"]
            raw_name = collapse_space(row.get(name_col, ""))
            is_continuation_name = not raw_name or raw_name.casefold().startswith("abilit")
            if raw_name:
                price = maybe_extract_price(raw_name)
                if price is not None:
                    current_prices[name_col] = price
                    active_definitions[name_col] = None
                    continue

            if is_continuation_name:
                active = active_definitions[name_col]
                if active is None:
                    continue
                effect_values = [
                    collapse_space(row.get(column, ""))
                    for column in iter_columns(spec["rank_col"], spec["block_end_col"])
                ]
                active["effects"] = normalize_effects(
                    [
                        *active["effects"],
                        *[
                            value
                            for value in effect_values
                            if not value.casefold().startswith("abilit")
                        ],
                    ]
                )
                continue

            current_price = current_prices[name_col]
            if current_price is None:
                continue
            rank = collapse_space(row.get(spec["rank_col"], ""))
            if not rank:
                continue
            context = f'Familiars "{raw_name}"'
            definition = build_equipment_definition(
                name=raw_name,
                family="familiar",
                category="equipment",
                rank=rank,
                buy_price=current_price,
                max_hp=parse_max_hp(row.get(spec["hp_col"], ""), f"{context} HP"),
                stats=build_stats(row, header_row, spec["stat_cols"], context),
                effects=collect_block_effects(
                    row,
                    spec["name_col"],
                    spec["block_end_col"],
                    {spec["name_col"], spec["rank_col"], spec["hp_col"], *spec["stat_cols"]},
                ),
            )
            definitions.append(definition)
            active_definitions[name_col] = definition

    return definitions


def parse_accessory_base_definitions(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    current_family: str | None = None
    current_price: int | None = None
    ring_price: int | None = None
    necklace_price: int | None = None
    imbue_fee: int | None = None
    pending: list[dict[str, object]] = []

    for row in rows[1:]:
        name = collapse_space(row.get("A", ""))
        rank_or_price = collapse_space(row.get("B", ""))
        lower_name = name.casefold()
        if lower_name == "ring":
            current_family = "ring"
            current_price = extract_price(rank_or_price, 'Accessories "Ring"')
            ring_price = current_price
            continue
        if lower_name == "necklace":
            current_family = "necklace"
            current_price = extract_price(rank_or_price, 'Accessories "Necklace"')
            necklace_price = current_price
            continue
        if lower_name == "imbuement":
            imbue_fee = extract_price(rank_or_price, 'Accessories "Imbuement"')
            current_family = None
            current_price = None
            continue
        if not name or ACCESSORY_GEM_RE.fullmatch(name) is not None or current_family is None or current_price is None:
            continue
        if current_family == "ring" and "ring" not in lower_name:
            continue
        if current_family == "necklace" and "necklace" not in lower_name:
            continue
        if not rank_or_price:
            continue
        pending.append(
            {
                "name": name,
                "family": current_family,
                "rank": rank_or_price,
                "buy_price": current_price,
                "effects": normalize_effects([row.get("C", ""), row.get("D", ""), row.get("E", "")]),
            }
        )

    if ring_price is None:
        raise ImportErrorWithContext("Accessories sheet is missing the Ring base price marker")
    if necklace_price is None:
        raise ImportErrorWithContext("Accessories sheet is missing the Necklace base price marker")
    if imbue_fee is None:
        raise ImportErrorWithContext("Accessories sheet is missing the Imbuement price marker")

    definitions: list[dict[str, object]] = []
    for item in pending:
        socket_policy = {
            "min_gems": 0 if item["family"] == "ring" else 1,
            "max_gems": 1 if item["family"] == "ring" else 3,
            "imbue_fee": imbue_fee,
        }
        definitions.append(
            build_equipment_definition(
                name=item["name"],
                family=item["family"],
                category=infer_equipment_category(item["family"], ACCESSORIES_SHEET),
                rank=item["rank"],
                buy_price=item["buy_price"],
                max_hp=None,
                stats={},
                effects=item["effects"],
                socket_policy=socket_policy,
            )
        )
    return definitions


def parse_accessory_right_side(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    current_family: str | None = "shield" if collapse_space(rows[0].get("H", "")).casefold() == "shields" else None
    current_price: int | None = None
    definitions: list[dict[str, object]] = []

    for row in rows[1:]:
        name = collapse_space(row.get("H", ""))
        if not name:
            continue
        lower_name = name.casefold()
        if lower_name == "shields":
            current_family = "shield"
            current_price = None
            continue
        if lower_name == "talismans":
            current_family = "talisman"
            current_price = None
            continue
        price = maybe_extract_price(name)
        if price is not None:
            current_price = price
            continue
        if current_family is None or current_price is None:
            continue
        rank = collapse_space(row.get("I", ""))
        if not rank:
            continue
        context = f'Accessories "{name}"'
        definitions.append(
            build_equipment_definition(
                name=name,
                family=current_family,
                category=infer_equipment_category(current_family, ACCESSORIES_SHEET),
                rank=rank,
                buy_price=current_price,
                max_hp=parse_max_hp(row.get("J", ""), f"{context} HP", allow_null_markers=True),
                stats={},
                effects=normalize_effects([row.get("K", ""), row.get("L", ""), row.get("M", ""), row.get("N", ""), row.get("O", "")]),
            )
        )
    return definitions


def parse_accessory_equipment(rows_by_sheet: dict[str, list[dict[str, str]]]) -> list[dict[str, object]]:
    rows = rows_by_sheet[ACCESSORIES_SHEET]
    return parse_accessory_base_definitions(rows) + parse_accessory_right_side(rows)


def parse_equipment_definitions(rows_by_sheet: dict[str, list[dict[str, str]]]) -> dict[str, dict[str, object]]:
    dual_sheet_specs = {
        "Axes&Spears": (
            {
                "name_col": "A",
                "rank_col": "B",
                "hp_col": "C",
                "stat_cols": ("D", "E", "F"),
                "block_end_col": "H",
                "family_headers": {"axes": "axe"},
            },
            {
                "name_col": "I",
                "rank_col": "J",
                "hp_col": "K",
                "stat_cols": ("L", "M", "N"),
                "block_end_col": "O",
                "family_headers": {"spears": "spear"},
            },
        ),
        "Swords&Bows": (
            {
                "name_col": "A",
                "rank_col": "B",
                "hp_col": "C",
                "stat_cols": ("D", "E", "F"),
                "block_end_col": "I",
                "family_headers": {"swords": "sword"},
            },
            {
                "name_col": "J",
                "rank_col": "K",
                "hp_col": "L",
                "stat_cols": ("M", "N", "O"),
                "block_end_col": "P",
                "family_headers": {"bows": "bow"},
            },
        ),
        "Light&Heavy ": (
            {
                "name_col": "A",
                "rank_col": "B",
                "hp_col": "C",
                "stat_cols": ("D", "E"),
                "block_end_col": "H",
                "family_headers": {"light armor": "light_armor"},
            },
            {
                "name_col": "I",
                "rank_col": "J",
                "hp_col": "K",
                "stat_cols": ("L", "M"),
                "block_end_col": "Q",
                "family_headers": {"heavy armor": "heavy_armor"},
            },
        ),
        "Robe&Hide": (
            {
                "name_col": "A",
                "rank_col": "B",
                "hp_col": "C",
                "stat_cols": ("D", "E"),
                "block_end_col": "J",
                "family_headers": {"robe armor": "robe_armor"},
            },
            {
                "name_col": "K",
                "rank_col": "L",
                "hp_col": "M",
                "stat_cols": ("N", "O"),
                "block_end_col": "V",
                "family_headers": {"hide armor": "hide_armor"},
            },
        ),
        "Headware": (
            {
                "name_col": "A",
                "rank_col": "B",
                "hp_col": "C",
                "stat_cols": ("D",),
                "block_end_col": "H",
                "family_headers": {
                    "light helms": "light_helm",
                    "heavy helms": "heavy_helm",
                },
            },
            {
                "name_col": "I",
                "rank_col": "J",
                "hp_col": "K",
                "stat_cols": ("L",),
                "block_end_col": "P",
                "family_headers": {
                    "mage helms": "mage_helm",
                    "golem heads": "golem_head",
                },
            },
        ),
    }
    single_sheet_specs = {
        "Staves&Orbs": {
            "name_col": "A",
            "rank_col": "B",
            "hp_col": "C",
            "stat_cols": ("D", "E", "F"),
            "block_end_col": "J",
            "family_headers": {
                "staves": "staff_orb",
                "orbs": "orb",
            },
        },
        "Runestones": {
            "name_col": "A",
            "rank_col": "B",
            "hp_col": "C",
            "stat_cols": ("D", "E", "F"),
            "block_end_col": "J",
            "family_headers": {"runestones": "runestone"},
        },
        "Golem&Gauntlet": {
            "family": "golem_armor",
            "name_col": "A",
            "rank_col": "B",
            "hp_col": "C",
            "stat_cols": ("D", "E"),
            "block_end_col": "H",
            "family_headers": {"golem armor": "golem_armor"},
            "item_family_override": lambda name, active_family: "gauntlet"
            if "gauntlet" in name.casefold()
            else active_family,
        },
        "Footwear": {
            "name_col": "A",
            "rank_col": "B",
            "hp_col": "C",
            "stat_cols": ("D", "E"),
            "block_end_col": "J",
            "family_headers": {
                "light boots": "footwear",
                "heavy boots": "footwear",
            },
        },
        "Mounts&Legs": {
            "name_col": "A",
            "rank_col": "B",
            "hp_col": "I",
            "stat_cols": ("C", "D", "E", "F", "G", "H", "J", "K"),
            "block_end_col": "Q",
            "family_headers": {
                "mount": "mount",
                "golem": "golem_legs",
            },
        },
    }

    definitions: list[dict[str, object]] = []
    for sheet_name, specs in dual_sheet_specs.items():
        for spec in specs:
            definitions.extend(parse_standard_equipment_block(rows_by_sheet[sheet_name], sheet_name, spec))
    for sheet_name, spec in single_sheet_specs.items():
        definitions.extend(parse_standard_equipment_block(rows_by_sheet[sheet_name], sheet_name, spec))
    definitions.extend(parse_familiars_sheet(rows_by_sheet["Familiars"]))
    definitions.extend(parse_accessory_equipment(rows_by_sheet))

    output: dict[str, dict[str, object]] = {}
    seen_names: set[str] = set()
    for definition in definitions:
        key = definition["name"].casefold()
        if key in seen_names:
            raise ImportErrorWithContext(f'Duplicate equipment definition after normalization: {definition["name"]}')
        seen_names.add(key)
        output[definition["name"]] = definition
    return dict(sorted(output.items(), key=lambda item: item[0].casefold()))


def parse_subtypes(rows_by_sheet: dict[str, list[dict[str, str]]]) -> dict[str, dict[str, str]]:
    subtype_map: dict[str, dict[str, str]] = {}
    legend_lookup = {label.casefold(): key for key, label in POTION_SUBTYPE_LABELS.items()}
    for sheet_name in POTION_SHEETS:
        current: dict[str, dict[str, str]] = {}
        for row in rows_by_sheet[sheet_name]:
            label = collapse_space(row.get("A", ""))
            key = legend_lookup.get(label.casefold())
            if key is None:
                continue
            current[key] = {
                "label": POTION_SUBTYPE_LABELS[key],
                "action_text": collapse_space(row.get("B", "")),
                "targeting_text": collapse_space(row.get("E", "")),
            }
        if set(current) != set(legend_lookup.values()):
            missing = sorted(set(legend_lookup.values()) - set(current))
            raise ImportErrorWithContext(f"Subtype legend missing entries in {sheet_name}: {', '.join(missing)}")
        if not subtype_map:
            subtype_map = current
            continue
        if subtype_map != current:
            raise ImportErrorWithContext(f"Subtype legend mismatch between potion sheets and {sheet_name}")
    return subtype_map


def parse_potion_recipes(
    rows_by_sheet: dict[str, list[dict[str, str]]],
    ingredient_aliases: dict[str, str],
    output_aliases: dict[str, str],
) -> list[dict]:
    recipes: list[dict] = []
    seen_names: set[str] = set()
    for sheet_name in POTION_SHEETS:
        for row in rows_by_sheet[sheet_name]:
            name = collapse_space(row.get("A", ""))
            price_text = collapse_space(row.get("C", ""))
            if not name and not price_text:
                continue
            if not name or not price_text.isdigit():
                continue
            canonical_name = apply_alias(name, output_aliases)
            if canonical_name.casefold() in seen_names:
                raise ImportErrorWithContext(f"Duplicate recipe after alias normalization: {canonical_name}")
            seen_names.add(canonical_name.casefold())

            effect_text = collapse_space(row.get("H", ""))
            if not effect_text:
                raise ImportErrorWithContext(f"Recipe {canonical_name!r} is missing effect text")

            ingredients: Counter[str] = Counter()
            for column in ("D", "E", "F", "G"):
                parsed = parse_ingredient_cell(row.get(column, ""))
                if parsed is None:
                    continue
                ingredient_name, count = parsed
                ingredients[apply_alias(ingredient_name, ingredient_aliases)] += count

            if not ingredients:
                raise ImportErrorWithContext(f"Recipe {canonical_name!r} has no parsed ingredients")

            infer_potion_subtype(canonical_name)
            recipes.append(
                {
                    "name": canonical_name,
                    "kind": "potion",
                    "tier": normalize_tier(row.get("B", "")),
                    "price": int(price_text),
                    "ingredients": dict(sorted(ingredients.items(), key=lambda item: item[0].casefold())),
                    "effect_text": effect_text,
                }
            )
    return sorted(recipes, key=lambda recipe: recipe["name"].casefold())


def parse_ingredient_prices(
    rows_by_sheet: dict[str, list[dict[str, str]]],
    ingredient_aliases: dict[str, str],
    known_ingredient_names: dict[str, str],
) -> dict[str, int]:
    prices: dict[str, int] = {}
    current_price: int | None = None
    for row in rows_by_sheet[INGREDIENT_SHEET]:
        marker = collapse_space(row.get("B", ""))
        match = PRICE_RE.fullmatch(marker)
        if match is not None:
            current_price = int(match.group(1))
            continue
        if current_price is None:
            continue
        for column in ("B", "D", "F", "H", "J"):
            raw_name = collapse_space(row.get(column, ""))
            if not raw_name:
                continue
            if raw_name.lower().endswith(" gold"):
                continue
            if len(raw_name) == 1 and raw_name.isalpha():
                continue
            if raw_name.casefold() == "ingrediants":
                continue
            candidate = PIECE_SUFFIX_MARKER_RE.sub(r"\1", raw_name)
            candidate = apply_alias(candidate, ingredient_aliases)
            canonical = known_ingredient_names.get(candidate.casefold())
            if canonical is None:
                continue
            previous = prices.get(canonical)
            if previous is not None and previous != current_price:
                raise ImportErrorWithContext(
                    f"Ingredient {canonical!r} has conflicting workbook prices {previous} and {current_price}"
                )
            prices[canonical] = current_price
    missing = sorted(name for name in known_ingredient_names.values() if name not in prices)
    if missing:
        raise ImportErrorWithContext(f"Workbook price sheet is missing prices for: {', '.join(missing)}")
    return dict(sorted(prices.items(), key=lambda item: item[0].casefold()))


def generate_gem_recipes(ingredient_names: list[str]) -> list[dict]:
    gem_recipes: list[dict] = []
    for ingredient_name in sorted(ingredient_names, key=str.casefold):
        if not ingredient_name.endswith(" piece"):
            continue
        gem_name = ingredient_name.removesuffix(" piece")
        gem_recipes.append(
            {
                "name": gem_name,
                "kind": "gem",
                "ingredients": {ingredient_name: 5},
            }
        )
    return gem_recipes


def parse_gem_metadata(
    rows_by_sheet: dict[str, list[dict[str, str]]],
    output_aliases: dict[str, str],
    known_gem_names: dict[str, str],
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    for row in rows_by_sheet[ACCESSORIES_SHEET]:
        raw_name = collapse_space(row.get("A", ""))
        if not raw_name:
            continue
        match = ACCESSORY_GEM_RE.fullmatch(raw_name)
        if match is None:
            continue
        canonical_name = apply_alias(match.group(1), output_aliases)
        gem_name = known_gem_names.get(canonical_name.casefold())
        if gem_name is None:
            raise ImportErrorWithContext(f"Accessories sheet references unknown gem {raw_name!r}")
        if gem_name in metadata:
            raise ImportErrorWithContext(f"Accessories sheet has duplicate metadata for gem {gem_name!r}")
        god = collapse_space(match.group(2))
        color = collapse_space(row.get("F", ""))
        accessory_effects = [
            collapse_space(row.get(column, ""))
            for column in ("C", "D", "E")
            if collapse_space(row.get(column, ""))
        ]
        if not god:
            raise ImportErrorWithContext(f"Accessories sheet gem {gem_name!r} is missing a god name")
        if not color:
            raise ImportErrorWithContext(f"Accessories sheet gem {gem_name!r} is missing a color")
        if not accessory_effects:
            raise ImportErrorWithContext(f"Accessories sheet gem {gem_name!r} is missing accessory effects")
        metadata[gem_name] = {
            "color": color,
            "god": god,
            "accessory_effects": accessory_effects,
        }
    missing = sorted(name for name in known_gem_names.values() if name not in metadata)
    if missing:
        raise ImportErrorWithContext(f"Accessories sheet is missing gem metadata for: {', '.join(missing)}")
    return dict(sorted(metadata.items(), key=lambda item: item[0].casefold()))


def normalize_equipment_inventory(
    raw_inventory: list[dict[str, object]] | None,
    equipment_definitions: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    instances: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, raw_entry in enumerate(raw_inventory or []):
        if not isinstance(raw_entry, dict):
            raise ImportErrorWithContext(f"inventory.equipment[{index}] must be a table")
        instance_id = collapse_space(raw_entry.get("id", ""))
        if not instance_id:
            raise ImportErrorWithContext(f"inventory.equipment[{index}] is missing id")
        if instance_id in seen_ids:
            raise ImportErrorWithContext(f'inventory.equipment contains duplicate id "{instance_id}"')
        seen_ids.add(instance_id)
        base_name = collapse_space(raw_entry.get("base_name", ""))
        if base_name not in equipment_definitions:
            raise ImportErrorWithContext(f'inventory.equipment[{index}] references unknown equipment "{base_name}"')
        definition = equipment_definitions[base_name]
        has_current_hp = "current_hp" in raw_entry
        raw_current_hp = raw_entry.get("current_hp")
        current_hp: int | None
        if raw_current_hp is None or raw_current_hp == "":
            current_hp = None
        else:
            current_hp = int(raw_current_hp)
        if definition["max_hp"] is None:
            if current_hp is not None and current_hp < 0:
                raise ImportErrorWithContext(f'inventory.equipment[{index}] current_hp must not be negative for "{base_name}"')
        else:
            if not has_current_hp or current_hp is None:
                raise ImportErrorWithContext(
                    f'inventory.equipment[{index}] current_hp is required for "{base_name}"'
                )
            if current_hp < 0 or current_hp > definition["max_hp"]:
                raise ImportErrorWithContext(
                    f'inventory.equipment[{index}] current_hp must be between 0 and {definition["max_hp"]} for "{base_name}"'
                )
        instances.append(
            {
                "id": instance_id,
                "base_name": base_name,
                "current_hp": current_hp,
            }
        )
    return instances


def normalize_resources(
    raw_resources: dict,
    known_ingredient_names: dict[str, str],
    known_output_names: dict[str, str],
    equipment_definitions: dict[str, dict[str, object]],
) -> dict:
    gold = int(raw_resources.get("gold", 0))
    if gold < 0:
        raise ImportErrorWithContext("Starting gold cannot be negative")
    market = raw_resources.get("market", {})
    sell_markdown = float(market.get("sell_markdown", 0.5))
    if sell_markdown < 0 or sell_markdown > 1:
        raise ImportErrorWithContext("market.sell_markdown must be between 0 and 1")

    inventory = raw_resources.get("inventory", {})
    output_names = dict(known_output_names)
    ingredients = normalize_counter_keys(
        inventory.get("ingredients", {}),
        {},
        known_ingredient_names,
        "inventory.ingredients",
    )
    potions = normalize_counter_keys(
        inventory.get("potions", {}),
        {},
        output_names,
        "inventory.potions",
    )
    gems = normalize_counter_keys(
        inventory.get("gems", {}),
        {},
        output_names,
        "inventory.gems",
    )
    equipment = normalize_equipment_inventory(inventory.get("equipment", []), equipment_definitions)

    sold_ingredients = normalize_flag_keys(
        raw_resources.get("for_sale", {}).get("ingredients", {}),
        {},
        known_ingredient_names,
        "for_sale.ingredients",
    )
    sold_outputs = normalize_flag_keys(
        raw_resources.get("for_sale", {}).get("outputs", {}),
        {},
        known_output_names,
        "for_sale.outputs",
    )
    sold_equipment = normalize_flag_keys(
        raw_resources.get("for_sale", {}).get("equipment", {}),
        {},
        {name.casefold(): name for name in equipment_definitions},
        "for_sale.equipment",
    )

    return {
        "market": {
            "sell_markdown": sell_markdown,
        },
        "inventory": {
            "gold": gold,
            "ingredients": ingredients,
            "potions": potions,
            "gems": gems,
            "equipment": equipment,
        },
        "for_sale": {
            "ingredients": sold_ingredients,
            "outputs": sold_outputs,
            "equipment": sold_equipment,
        },
    }


def build_known_names(recipes: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    ingredient_names = sorted(
        {ingredient for recipe in recipes for ingredient in recipe["ingredients"]},
        key=str.casefold,
    )
    output_names = sorted((recipe["name"] for recipe in recipes), key=str.casefold)
    return (
        {name.casefold(): name for name in ingredient_names},
        {name.casefold(): name for name in output_names},
    )


def build_ingredient_types(scenario: dict) -> dict[str, str]:
    names: set[str] = set()
    names.update(scenario["inventory"]["ingredients"])
    names.update(scenario["ingredient_prices"])
    for recipe in scenario["recipes"]["recipes"]:
        names.update(recipe["ingredients"])
    return {
        name: ("gem_piece" if name.endswith(" piece") else "herb")
        for name in sorted(names, key=str.casefold)
    }


def import_workbook(workbook_path: Path, alias_path: Path, resources_path: Path) -> dict:
    alias_data = load_toml(alias_path)
    ingredient_aliases = build_alias_map(alias_data.get("ingredients", {}), "ingredient")
    output_aliases = build_alias_map(alias_data.get("outputs", {}), "output")

    rows_by_sheet = read_workbook(workbook_path)
    missing_sheets = [name for name in (*POTION_SHEETS, INGREDIENT_SHEET, *EQUIPMENT_SHEETS) if name not in rows_by_sheet]
    if missing_sheets:
        raise ImportErrorWithContext(f"Workbook is missing sheets: {', '.join(missing_sheets)}")

    subtypes = parse_subtypes(rows_by_sheet)
    potion_recipes = parse_potion_recipes(rows_by_sheet, ingredient_aliases, output_aliases)
    known_ingredients, _ = build_known_names(potion_recipes)
    ingredient_prices = parse_ingredient_prices(rows_by_sheet, ingredient_aliases, known_ingredients)
    gem_recipes = generate_gem_recipes(list(ingredient_prices))
    gem_metadata = parse_gem_metadata(
        rows_by_sheet,
        output_aliases,
        {recipe["name"].casefold(): recipe["name"] for recipe in gem_recipes},
    )
    equipment_definitions = parse_equipment_definitions(rows_by_sheet)
    all_recipes = sorted(potion_recipes + gem_recipes, key=lambda recipe: recipe["name"].casefold())

    all_ingredient_names, all_output_names = build_known_names(all_recipes)
    resources = normalize_resources(
        load_toml(resources_path),
        all_ingredient_names,
        all_output_names,
        equipment_definitions,
    )

    scenario = {
        "market": resources["market"],
        "inventory": resources["inventory"],
        "ingredient_prices": ingredient_prices,
        "ingredient_types": {},
        "gem_metadata": gem_metadata,
        "equipment": {"definitions": equipment_definitions},
        "for_sale": resources["for_sale"],
        "subtypes": subtypes,
        "recipes": {"recipes": all_recipes},
    }
    scenario["ingredient_types"] = build_ingredient_types(scenario)
    return scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the Awesome Heroes workbook into Poshy seed JSON.")
    parser.add_argument("--workbook", type=Path, required=True, help="Path to the workbook .xlsx file.")
    parser.add_argument("--aliases", type=Path, required=True, help="Path to the alias TOML file.")
    parser.add_argument("--resources", type=Path, required=True, help="Path to the starting resources TOML file.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the generated scenario JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario = import_workbook(args.workbook, args.aliases, args.resources)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(scenario, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

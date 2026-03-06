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
PRICE_RE = re.compile(r"^\s*(\d+)\s*Gold\s*$", re.IGNORECASE)
INGREDIENT_RE = re.compile(r"^(.*?)\s*\((\d+)\)$")
RANK_RE = re.compile(r"^\s*([A-Z])(?:\s|$)")
PIECE_SUFFIX_MARKER_RE = re.compile(r"^(.*?\bpiece)\s+[A-Z]$", re.IGNORECASE)
CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")
ACCESSORY_GEM_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")

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


class ImportErrorWithContext(RuntimeError):
    pass


def collapse_space(value: str) -> str:
    return " ".join(str(value).strip().split())


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


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


def normalize_resources(
    raw_resources: dict,
    known_ingredient_names: dict[str, str],
    known_output_names: dict[str, str],
) -> dict:
    gold = int(raw_resources.get("gold", 0))
    if gold < 0:
        raise ImportErrorWithContext("Starting gold cannot be negative")

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

    return {
        "inventory": {
            "gold": gold,
            "ingredients": ingredients,
            "potions": potions,
            "gems": gems,
        },
        "for_sale": {
            "ingredients": sold_ingredients,
            "outputs": sold_outputs,
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
    missing_sheets = [name for name in (*POTION_SHEETS, INGREDIENT_SHEET, ACCESSORIES_SHEET) if name not in rows_by_sheet]
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
    all_recipes = sorted(potion_recipes + gem_recipes, key=lambda recipe: recipe["name"].casefold())

    all_ingredient_names, all_output_names = build_known_names(all_recipes)
    resources = normalize_resources(
        load_toml(resources_path),
        all_ingredient_names,
        all_output_names,
    )

    scenario = {
        "inventory": resources["inventory"],
        "ingredient_prices": ingredient_prices,
        "ingredient_types": {},
        "gem_metadata": gem_metadata,
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

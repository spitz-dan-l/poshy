from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_PATH = REPO_ROOT / "Awesome Heroes Items.xlsx"
ALIASES_PATH = REPO_ROOT / "data/workbook_aliases.toml"
RESOURCES_PATH = REPO_ROOT / "data/starting_resources.toml"
IMPORTER_PATH = REPO_ROOT / "scripts/import_workbook.py"


def run_importer(
    tmp_path: Path,
    *,
    aliases_path: Path = ALIASES_PATH,
    resources_path: Path = RESOURCES_PATH,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    output_path = tmp_path / "scenario.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(IMPORTER_PATH),
            "--workbook",
            str(WORKBOOK_PATH),
            "--aliases",
            str(aliases_path),
            "--resources",
            str(resources_path),
            "--out",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return completed, output_path


def test_import_workbook_generates_expected_schema(tmp_path: Path) -> None:
    completed, output_path = run_importer(tmp_path)
    assert completed.returncode == 0, completed.stderr

    data = json.loads(output_path.read_text(encoding="utf-8"))
    recipes = data["recipes"]["recipes"]
    potions = [recipe for recipe in recipes if recipe["kind"] == "potion"]
    gems = [recipe for recipe in recipes if recipe["kind"] == "gem"]
    equipment = data["equipment"]["definitions"]

    assert len(potions) == 60
    assert len(gems) == 20
    assert len(equipment) == 353
    assert set(data["subtypes"]) == {"medicine", "elixir", "potion", "toxin", "solution", "grenade", "brew"}

    warming = next(recipe for recipe in recipes if recipe["name"] == "Warming medicine")
    assert warming["price"] == 45
    assert warming["tier"] == "D"
    assert warming["effect_text"]
    assert "subtype" not in warming

    miracle = next(recipe for recipe in recipes if recipe["name"] == "Miracle medicine")
    assert miracle["price"] == 150

    agate = next(recipe for recipe in recipes if recipe["name"] == "Agate")
    assert agate["ingredients"] == {"Agate piece": 5}
    assert "subtype" not in agate
    assert "tier" not in agate
    assert "price" not in agate
    assert "effect_text" not in agate
    assert data["gem_metadata"]["Agate"] == {
        "color": "Violet",
        "god": "golem +",
        "accessory_effects": ["gain 2MP every turn you don't cast a spell"],
    }

    assert data["inventory"]["ingredients"]["Agate piece"] == 0
    assert data["inventory"]["ingredients"]["Lapis lazuli piece"] == 9
    assert data["inventory"]["equipment"] == [
        {"id": "ring-bronze-1", "base_name": "Bronze ring", "current_hp": None},
        {"id": "shield-basic-1", "base_name": "Basic Iron Shield", "current_hp": 7},
        {"id": "boots-leather-1", "base_name": "Leather Shoes", "current_hp": 7},
        {"id": "talisman-silver-1", "base_name": "Silver Talisman", "current_hp": None},
    ]
    assert data["ingredient_prices"]["Agate piece"] == 20
    assert data["for_sale"]["ingredients"]["Agate piece"] is True
    assert data["for_sale"]["outputs"]["Dark Toxin"] is True
    assert data["for_sale"]["equipment"] == {
        "Basic Iron Shield": True,
        "Bronze ring": True,
        "Leather Shoes": True,
        "Silver Talisman": True,
    }
    assert data["market"] == {"sell_markdown": 0.5}
    assert data["ingredient_types"]["Diamond piece"] == "gem_piece"
    assert data["ingredient_types"]["Dragon scale"] == "herb"

    assert equipment["Iron Axe"]["family"] == "axe"
    assert equipment["Iron Spear"]["family"] == "spear"
    assert equipment["Oaken Short Bow"]["family"] == "bow"
    assert equipment["Elder Staff"]["family"] == "staff_orb"
    assert equipment["Blue Orb"]["family"] == "orb"
    assert equipment["Leather Cuirass"]["family"] == "light_armor"
    assert equipment["Iron Plate Armor"]["family"] == "heavy_armor"
    assert equipment["Bishop Robe"]["family"] == "robe_armor"
    assert equipment["Bear Hide"]["family"] == "hide_armor"
    assert equipment["Common Carapace"]["family"] == "golem_armor"
    assert equipment["Basic Work Hat"]["family"] == "heavy_helm"
    assert equipment["Apprentice's Hat"]["family"] == "mage_helm"
    assert equipment["Prized Camel"]["family"] == "mount"
    assert equipment["Basic Legs"]["family"] == "golem_legs"
    assert equipment["Leather Gauntlets"]["family"] == "gauntlet"
    assert equipment["Ape"]["rank"] == "B"
    assert equipment["Eagle"]["rank"] == "A"

    assert equipment["Ape"]["family"] == "familiar"
    assert equipment["Ape"]["effects"] == [
        "Climbing cap increased by 3",
        "Can pick up one item",
        "Knocks back opponents for half damage dealt",
        "Chest beat (5MP) (ran: 3 all directions) (Acc: 18) increases attack by 1 and scares away enemies",
    ]

    assert equipment["Bronze ring"] == {
        "name": "Bronze ring",
        "family": "ring",
        "category": "accessory",
        "rank": "A",
        "buy_price": 40,
        "max_hp": None,
        "stats": {},
        "effects": ["+1 STR cap", "-1 SKI cap"],
        "socket_policy": {
            "min_gems": 0,
            "max_gems": 1,
            "imbue_fee": 50,
        },
    }
    assert equipment["Bronze necklace"] == {
        "name": "Bronze necklace",
        "family": "necklace",
        "category": "accessory",
        "rank": "A",
        "buy_price": 150,
        "max_hp": None,
        "stats": {},
        "effects": ["+1 SKI cap", "-1 WIS cap"],
        "socket_policy": {
            "min_gems": 1,
            "max_gems": 3,
            "imbue_fee": 50,
        },
    }
    assert equipment["Basic Iron Shield"]["family"] == "shield"
    assert equipment["Basic Iron Shield"]["category"] == "equipment"
    assert equipment["Basic Iron Shield"]["max_hp"] == 7
    assert equipment["Basic Iron Shield"]["effects"][:2] == ["Shield block", "Increases shield by 1"]
    assert equipment["Silver Talisman"] == {
        "name": "Silver Talisman",
        "family": "talisman",
        "category": "accessory",
        "rank": "C",
        "buy_price": 130,
        "max_hp": None,
        "stats": {},
        "effects": ["1/6 chance of preventiing damage"],
    }
    assert "source_sheet" not in equipment["Bronze ring"]
    assert "source_sheet" not in equipment["Basic Iron Shield"]
    assert "source_sheet" not in equipment["Silver Talisman"]


def test_import_workbook_rejects_unknown_resource_names(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]
"Unknown Mushroom" = 1

[inventory.potions]

[inventory.gems]

[for_sale.ingredients]

[for_sale.outputs]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert "unknown name" in completed.stderr.lower()


def test_import_workbook_rejects_resource_alias_names(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources_alias.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]
"Agate" = 1

[inventory.potions]

[inventory.gems]

[for_sale.ingredients]

[for_sale.outputs]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert "unknown name" in completed.stderr.lower()


def test_import_workbook_rejects_unknown_equipment_in_resources(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources_equipment.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]

[inventory.potions]

[inventory.gems]

[[inventory.equipment]]
id = "broken-1"
base_name = "Missing ring"

[for_sale.ingredients]

[for_sale.outputs]

[for_sale.equipment]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert 'unknown equipment "Missing ring"' in completed.stderr


def test_import_workbook_rejects_duplicate_equipment_ids(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources_duplicate_equipment.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]

[inventory.potions]

[inventory.gems]

[[inventory.equipment]]
id = "shield-1"
base_name = "Basic Iron Shield"
current_hp = 7

[[inventory.equipment]]
id = "shield-1"
base_name = "Leather Shoes"
current_hp = 7

[for_sale.ingredients]

[for_sale.outputs]

[for_sale.equipment]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert "duplicate id" in completed.stderr.lower()


def test_import_workbook_rejects_missing_equipment_hp(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources_missing_hp.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]

[inventory.potions]

[inventory.gems]

[[inventory.equipment]]
id = "shield-1"
base_name = "Basic Iron Shield"

[for_sale.ingredients]

[for_sale.outputs]

[for_sale.equipment]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert "current_hp is required" in completed.stderr


def test_import_workbook_rejects_invalid_equipment_hp(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources_invalid_hp.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]

[inventory.potions]

[inventory.gems]

[[inventory.equipment]]
id = "shield-1"
base_name = "Basic Iron Shield"
current_hp = 99

[for_sale.ingredients]

[for_sale.outputs]

[for_sale.equipment]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert "current_hp must be between 0 and 7" in completed.stderr


def test_import_workbook_rejects_unknown_for_sale_equipment(tmp_path: Path) -> None:
    bad_resources = tmp_path / "bad_resources_for_sale_equipment.toml"
    bad_resources.write_text(
        """
gold = 339

[inventory.ingredients]

[inventory.potions]

[inventory.gems]

[for_sale.ingredients]

[for_sale.outputs]

[for_sale.equipment]
"Missing ring" = true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, resources_path=bad_resources)
    assert completed.returncode != 0
    assert "for_sale.equipment references unknown name" in completed.stderr


def test_import_workbook_rejects_output_alias_collisions(tmp_path: Path) -> None:
    bad_aliases = tmp_path / "bad_aliases.toml"
    bad_aliases.write_text(
        ALIASES_PATH.read_text(encoding="utf-8")
        + '\n"Health potion" = "Mana potion"\n',
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, aliases_path=bad_aliases)
    assert completed.returncode != 0
    assert "duplicate recipe" in completed.stderr.lower()


def test_import_workbook_rejects_unmatched_subtype_names(tmp_path: Path) -> None:
    bad_aliases = tmp_path / "bad_subtype_aliases.toml"
    bad_aliases.write_text(
        ALIASES_PATH.read_text(encoding="utf-8")
        + '\n"Warming medicine" = "Warming tonic"\n',
        encoding="utf-8",
    )

    completed, _ = run_importer(tmp_path, aliases_path=bad_aliases)
    assert completed.returncode != 0
    assert "unable to infer potion subtype" in completed.stderr.lower()

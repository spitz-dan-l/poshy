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

    assert len(potions) == 60
    assert len(gems) == 20
    assert set(data["subtypes"]) == {"medicine", "elixir", "potion", "toxin", "solution", "grenade", "brew", "gem"}

    warming = next(recipe for recipe in recipes if recipe["name"] == "Warming medicine")
    assert warming["price"] == 45
    assert warming["tier"] == "D"
    assert warming["subtype"] == "medicine"
    assert warming["effect_text"]

    miracle = next(recipe for recipe in recipes if recipe["name"] == "Miracle medicine")
    assert miracle["price"] == 150

    agate = next(recipe for recipe in recipes if recipe["name"] == "Agate")
    assert agate["tier"] == "X"
    assert agate["price"] is None
    assert agate["effect_text"] == ""
    assert agate["ingredients"] == {"Agate piece": 5}

    assert data["inventory"]["ingredients"]["Agate piece"] == 0
    assert data["inventory"]["ingredients"]["Lapis lazuli piece"] == 9
    assert data["for_sale"]["ingredients"]["Agate piece"] == 20
    assert isinstance(data["for_sale"]["ingredients"]["Agate piece"], int)
    assert data["for_sale"]["outputs"]["Dark Toxin"] is True

    assert data["ingredient_types"]["Diamond piece"] == "gem_piece"
    assert data["ingredient_types"]["Dragon scale"] == "herb"


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

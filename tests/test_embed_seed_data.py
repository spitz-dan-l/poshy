from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EMBEDDER_PATH = REPO_ROOT / "scripts/embed_seed_data.py"
SEED_JSON_PATH = REPO_ROOT / "data/seed_scenario.json"
INDEX_PATH = REPO_ROOT / "index.html"
START_MARKER = "<!-- poshy:seed-data:start -->"
END_MARKER = "<!-- poshy:seed-data:end -->"
SCRIPT_OPEN = '<script id="seed-data" type="application/json">'
SCRIPT_CLOSE = "  </script>"


def run_embedder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EMBEDDER_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def extract_embedded_seed_json(html_text: str) -> str:
    script_start = html_text.index(SCRIPT_OPEN)
    json_start = html_text.index("\n", script_start) + 1
    script_end = html_text.index(f"\n{SCRIPT_CLOSE}", json_start)
    return html_text[json_start:script_end]


def test_embed_seed_data_updates_marked_block(tmp_path: Path) -> None:
    html_path = tmp_path / "index.html"
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html>",
                "<body>",
                "  <!-- poshy:seed-data:start -->",
                '  <script id="seed-data" type="application/json">',
                '{"stale":true}',
                "  </script>",
                "  <!-- poshy:seed-data:end -->",
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    completed = run_embedder("--html", str(html_path), "--json", str(SEED_JSON_PATH))
    assert completed.returncode == 0, completed.stderr

    html_text = html_path.read_text(encoding="utf-8")
    assert START_MARKER in html_text
    assert END_MARKER in html_text
    assert "<!-- generated from data/seed_scenario.json by scripts/embed_seed_data.py -->" in html_text
    assert extract_embedded_seed_json(html_text) == SEED_JSON_PATH.read_text(encoding="utf-8").rstrip("\n")


def test_embed_seed_data_check_mode_detects_mismatch(tmp_path: Path) -> None:
    html_path = tmp_path / "index.html"
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html>",
                "<body>",
                "  <!-- poshy:seed-data:start -->",
                "  <!-- generated from data/seed_scenario.json by scripts/embed_seed_data.py -->",
                '  <script id="seed-data" type="application/json">',
                '{"stale":true}',
                "  </script>",
                "  <!-- poshy:seed-data:end -->",
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    mismatch = run_embedder("--check", "--html", str(html_path), "--json", str(SEED_JSON_PATH))
    assert mismatch.returncode == 1
    assert "out of sync" in mismatch.stdout

    updated = run_embedder("--html", str(html_path), "--json", str(SEED_JSON_PATH))
    assert updated.returncode == 0, updated.stderr

    in_sync = run_embedder("--check", "--html", str(html_path), "--json", str(SEED_JSON_PATH))
    assert in_sync.returncode == 0
    assert "is in sync" in in_sync.stdout


def test_repo_index_embedded_seed_matches_seed_file() -> None:
    html_text = INDEX_PATH.read_text(encoding="utf-8")
    assert START_MARKER in html_text
    assert END_MARKER in html_text
    assert extract_embedded_seed_json(html_text) == SEED_JSON_PATH.read_text(encoding="utf-8").rstrip("\n")

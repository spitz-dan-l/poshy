from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_PATH = REPO_ROOT / "data/seed_scenario.json"
DEFAULT_HTML_PATH = REPO_ROOT / "index.html"
START_MARKER = "<!-- poshy:seed-data:start -->"
END_MARKER = "<!-- poshy:seed-data:end -->"
GENERATED_NOTE = "<!-- generated from data/seed_scenario.json by scripts/embed_seed_data.py -->"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the embedded seed JSON block in index.html from data/seed_scenario.json."
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help="Path to the canonical scenario JSON file.",
    )
    parser.add_argument(
        "--html",
        dest="html_path",
        type=Path,
        default=DEFAULT_HTML_PATH,
        help="Path to the HTML file containing the marked seed-data block.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the marked block does not match the JSON file.",
    )
    return parser.parse_args()


def render_block(json_text: str, indent: str) -> str:
    clean_json = json_text.rstrip("\n")
    return "\n".join(
        [
            f"{indent}{START_MARKER}",
            f"{indent}{GENERATED_NOTE}",
            f'{indent}<script id="seed-data" type="application/json">',
            clean_json,
            f"{indent}</script>",
            f"{indent}{END_MARKER}",
        ]
    )


def splice_seed_block(html_text: str, json_text: str) -> str:
    start = html_text.find(START_MARKER)
    if start == -1:
        raise ValueError(f"Missing start marker: {START_MARKER}")
    end = html_text.find(END_MARKER, start)
    if end == -1:
        raise ValueError(f"Missing end marker: {END_MARKER}")

    line_start = html_text.rfind("\n", 0, start) + 1
    line_end = html_text.find("\n", end)
    if line_end == -1:
        line_end = len(html_text)

    indent = html_text[line_start:start]
    if indent.strip():
        raise ValueError("Seed-data marker line contains non-whitespace before the start marker.")

    replacement = render_block(json_text, indent)
    return html_text[:line_start] + replacement + html_text[line_end:]


def main() -> int:
    args = parse_args()
    json_text = args.json_path.read_text(encoding="utf-8")
    html_text = args.html_path.read_text(encoding="utf-8")
    updated_html = splice_seed_block(html_text, json_text)

    if args.check:
        if html_text != updated_html:
            print(
                f"{args.html_path} is out of sync with {args.json_path}. "
                "Run scripts/embed_seed_data.py to refresh it."
            )
            return 1
        print(f"{args.html_path} is in sync with {args.json_path}.")
        return 0

    if html_text != updated_html:
        args.html_path.write_text(updated_html, encoding="utf-8")
        print(f"Updated {args.html_path} from {args.json_path}.")
    else:
        print(f"No changes needed in {args.html_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

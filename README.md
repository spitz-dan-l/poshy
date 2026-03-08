# Poshy

Offline single-file potion and equipment lab for `Awesome Heroes Items.xlsx`.

This README is written primarily for coding agents working in this repo.

## Current Status

- Phase 1 is complete: shared simulator, strict scenario validation, workbench/history plumbing, and equipment-aware state all ship.
- Phase 2 is complete: workbook-driven equipment import, seed regeneration, Base Inventory equipment editing, workbench equipment visibility, and Catalog equipment definitions with `optimizer_auto_sell`.
- Phase 3 is complete: manual equipment market actions, Shop equipment sale toggles, and HP-aware equipment sell flows now ship.
- The March 8, 2026 UI pass is also shipped: the Workbench now has category tabs, the inspector covers every item class, and herbs/gem pieces can be bought directly from the Workbench.
- Phase 4 and later are still future work: combo assembly, broader selling, and planner/optimization.

The live baseline is:

- `6` workbench categories: potions, gems, herbs, gem pieces, equipment, accessories
- `60` potion recipes
- `20` gem recipes
- `10` sellable ingredients
- `353` equipment definitions
- `4` starting equipment instances
- `4` sellable equipment definitions

## Start Here

- [docs/data-model.md](/home/dan/dev/poshy/docs/data-model.md): canonical schema, import pipeline, current seed counts, validation rules.
- [docs/roadmap-equipment-market.md](/home/dan/dev/poshy/docs/roadmap-equipment-market.md): implementation status and future phases.
- [data/seed_scenario.json](/home/dan/dev/poshy/data/seed_scenario.json): generated canonical scenario blob.
- [index.html](/home/dan/dev/poshy/index.html): the app, runtime validator, editor UI, simulator, and embedded seed.
- [scripts/import_workbook.py](/home/dan/dev/poshy/scripts/import_workbook.py): workbook importer.
- [scripts/embed_seed_data.py](/home/dan/dev/poshy/scripts/embed_seed_data.py): syncs `data/seed_scenario.json` into `index.html`.

Deprecated:

- [poshy_summary.md](/home/dan/dev/poshy/poshy_summary.md) is legacy reference only and not current project documentation.
- [potions.py](/home/dan/dev/poshy/potions.py) is part of the old pipeline and should not be treated as the source of truth for current app behavior.

## Repo Map

- `Awesome Heroes Items.xlsx`: upstream workbook input.
- `data/workbook_aliases.toml`: workbook-only spelling normalization.
- `data/starting_resources.toml`: starting inventory, sale flags, and market config.
- `data/seed_scenario.json`: generated scenario blob.
- `docs/`: current project docs.
- `scripts/`: importer and embed utilities.
- `tests/`: importer, embed-sync, and browser smoke coverage.
- `index.html`: single-file app.

## Common Workflows

### 1. Inspect The Current State

Use these first:

```bash
git status --short
rg -n "phase 3|equipment|optimizer_auto_sell|for_sale.equipment" docs index.html scripts tests
```

Do not assume docs are current. Check them.

### 2. Change Workbook Import Or Scenario Shape

If you touch importer logic or any canonical schema:

```bash
uv run python scripts/import_workbook.py \
  --workbook 'Awesome Heroes Items.xlsx' \
  --aliases data/workbook_aliases.toml \
  --resources data/starting_resources.toml \
  --out data/seed_scenario.json

uv run python scripts/embed_seed_data.py --html index.html --json data/seed_scenario.json
```

Then run verification:

```bash
uv run pytest -q tests/test_import_workbook.py tests/test_embed_seed_data.py
```

If browser behavior changed, also run the browser suite:

```bash
/bin/bash -lc "UV_CACHE_DIR=.uv-cache PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers uv run pytest -q tests/test_index_smoke.py"
```

In sandboxed environments, Playwright may need to run outside the sandbox.

### 3. Change Browser UI Or Runtime Logic

Typical files:

- `index.html`
- `tests/test_index_smoke.py`
- possibly `docs/data-model.md`
- possibly `docs/roadmap-equipment-market.md`

If UI text or behavior changes, update docs in the same change if existing wording becomes false.

### 4. Add Or Change Starting Inventory

Edit:

- `data/starting_resources.toml`

Then regenerate:

```bash
uv run python scripts/import_workbook.py \
  --workbook 'Awesome Heroes Items.xlsx' \
  --aliases data/workbook_aliases.toml \
  --resources data/starting_resources.toml \
  --out data/seed_scenario.json

uv run python scripts/embed_seed_data.py --html index.html --json data/seed_scenario.json
```

### 5. Full Runtime Verification

This is the current high-signal suite:

```bash
/bin/bash -lc "UV_CACHE_DIR=.uv-cache PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers uv run pytest -q tests/test_import_workbook.py tests/test_embed_seed_data.py tests/test_index_smoke.py"
```

## Project Rules That Matter

- `data/seed_scenario.json` is generated, not hand-edited.
- The embedded seed block inside `index.html` must stay in sync with `data/seed_scenario.json`.
- `index.html` validates strict canonical scenario JSON. It does not alias or repair imported data.
- Equipment definitions come from workbook import.
- Standalone equipment instances come from `data/starting_resources.toml` or runtime editing.
- The shipped Workbench supports manual buys for herbs, gem pieces, potion direct buys, and sold equipment/accessories, plus manual sells for standalone equipment instances.
- No combo instances or socket editing ship yet.

## How Dan Likes To Work

These notes are based on repo instructions and recent sessions. No project-specific prior chat logs were found in this repo when this README was written on March 8, 2026.

- Execute, do not just propose, unless the request is explicitly for planning or discussion.
- Keep docs synced with shipped reality in the same change. Do not leave roadmap or schema docs describing placeholder behavior after the code has moved on.
- Regenerate derived artifacts when schema or seed inputs change. In this repo that usually means `data/seed_scenario.json` and the embedded seed block in `index.html`.
- Verify with tests instead of stopping at code edits. Importer changes should be backed by importer tests; UI/runtime changes should be backed by smoke coverage.
- Communicate directly and concisely. High-signal updates are preferred over long narration.
- Preserve unrelated worktree changes. Do not revert someone else's edits unless explicitly asked.
- Prefer exact dates and exact status labels in docs when roadmap state changes.
- If you cannot find requested historical context, say so plainly and proceed with the best local evidence instead of pretending you found it.

## When Updating Docs

Usually touch these together:

- [docs/data-model.md](/home/dan/dev/poshy/docs/data-model.md) for schema or pipeline changes.
- [docs/roadmap-equipment-market.md](/home/dan/dev/poshy/docs/roadmap-equipment-market.md) for status changes or phase-boundary changes.
- [README.md](/home/dan/dev/poshy/README.md) when the top-level agent workflow changes.

After doc-heavy changes, a useful stale-text sweep is:

```bash
rg -n 'placeholder|not authored in TOML yet|gem metadata only|only four workbook sheets' docs README.md index.html
```

## Known Boundaries

Do not accidentally implement future roadmap work without saying so.

Still out of scope today:

- ring/necklace combo assembly or disassembly
- manual ingredient, potion, or gem sell actions
- socket editing
- planner/optimization tab

If a requested change crosses one of those boundaries, check the roadmap first and either:

- implement it intentionally and update the roadmap/docs/tests, or
- keep the change within the current phase boundary.

# Poshy

Offline single-file potion and equipment lab for `Awesome Heroes Items.xlsx`.

This README is written primarily for coding agents working in this repo.

## Current Status

- Phase 1 is complete: shared simulator, strict scenario validation, workbench/history plumbing, and equipment-aware state all ship.
- Phase 2 is complete: workbook-driven equipment import, seed regeneration, Base Inventory equipment editing, workbench equipment visibility, and Catalog equipment definitions.
- Phase 3 is complete: manual equipment market actions, Shop equipment sale toggles, and HP-aware equipment sell flows now ship.
- Phase 4 is complete: ring and necklace combo assembly/disassembly ship, persist through scenario state, and are driven from the `Accessories` workbench tab.
- Phase 5 is complete: manual per-unit sells for ingredients, potions, and gems now ship from `Current Holdings`, including sell-value inspector details and undo/redo-safe history.
- The March 9, 2026 equipment UI cleanup is also shipped: holdings gear now renders as readable cards, equipment ids stay internal, and workbook ranks are normalized to single-letter tiers.
- Phase 6 is complete: the planner/optimization tab ships with goal lines, deterministic previews, player-owned repurpose rules, funding fallback, and apply-through-history behavior.

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
rg -n "phase 3|equipment|for_sale.equipment|planner" docs index.html scripts tests
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

### 6. Visual QA Screenshots

Use Playwright Chromium for screenshots. Do not use Firefox for repo visual QA.

If Chromium is not installed yet:

```bash
/bin/bash -lc "UV_CACHE_DIR=.uv-cache PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers uv run playwright install chromium"
```

Desktop baseline at `1440x810`:

```bash
/bin/bash -lc "UV_CACHE_DIR=.uv-cache PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers uv run python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={\"width\": 1440, \"height\": 810})
    page.goto('file:///home/dan/dev/poshy/index.html', wait_until='domcontentloaded')
    page.screenshot(path='/tmp/poshy-desktop.png', full_page=True)
    browser.close()
PY"
```

Mobile baseline at `430x932`:

```bash
/bin/bash -lc "UV_CACHE_DIR=.uv-cache PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers uv run python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={\"width\": 430, \"height\": 932}, is_mobile=True, device_scale_factor=2)
    page.goto('file:///home/dan/dev/poshy/index.html', wait_until='domcontentloaded')
    page.screenshot(path='/tmp/poshy-mobile.png', full_page=True)
    browser.close()
PY"
```

Mobile holdings view for holdings-table changes:

```bash
/bin/bash -lc "UV_CACHE_DIR=.uv-cache PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers uv run python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={\"width\": 430, \"height\": 932}, is_mobile=True, device_scale_factor=2)
    page.goto('file:///home/dan/dev/poshy/index.html', wait_until='domcontentloaded')
    page.locator('button[data-action=\"set-workbench-mobile-section\"][data-section=\"holdings\"]').click()
    page.screenshot(path='/tmp/poshy-mobile-holdings.png', full_page=True)
    browser.close()
PY"
```

Review screenshots for:

- horizontal overflow
- wrapped or clipped button labels
- crowded count/value/action rows in holdings
- broken row alignment or sticky headers
- visually noisy changes versus the current baseline

Thorough visual QA means more than one screenshot. Do not stop at the default landing view.

Minimum workflow:

1. Capture the desktop baseline at `1440x810`.
2. Scroll every container affected by the change before taking additional screenshots.
3. Capture mobile at `430x932`.
4. Switch mobile sections when relevant instead of only inspecting the default `Workbench` section.
5. Select representative items so the inspector state is also checked.

Minimum screenshots for UI changes:

- desktop default page
- desktop scrolled view of the affected panel
- desktop view with a representative item selected in the inspector
- mobile default `Workbench` section if workbench cards or filters changed
- mobile `Holdings` section if holdings rows, cards, or sell/buy controls changed
- mobile `Action Log` section if history cards, toasts, or undo/redo labels changed

Additional state coverage when relevant:

- search/filter text entered
- long names or long effect text visible
- enabled and disabled action buttons both visible
- empty-state rows or cards visible
- expanded drawers, dialogs, or mobile inspector sheets if the change affects them
- after scrolling far enough to reach lower sections, not just the first visible rows

For holdings-specific work:

- capture the top of `Current Holdings`
- scroll the holdings column to the middle and lower sections and capture again
- if stackable tables changed, inspect herbs, gem pieces, potions, and gems separately
- if gear cards changed, inspect both `Equipment` and `Accessories`

For workbench-specific work:

- switch to every affected category tab
- if cards changed, capture both the top of the list and a scrolled state
- if filters or scope chips changed, capture at least one filtered state

For mobile-specific work:

- verify the `Workbench`, `Holdings`, and `Action Log` mobile section buttons when any of those surfaces changed
- if the inspector is relevant, open it from the affected section and capture the sheet state too
- do not assume desktop fixes imply mobile fixes

## Project Rules That Matter

- `data/seed_scenario.json` is generated, not hand-edited.
- The embedded seed block inside `index.html` must stay in sync with `data/seed_scenario.json`.
- `index.html` validates strict canonical scenario JSON. It does not alias or repair imported data.
- Equipment definitions come from workbook import.
- Standalone equipment instances come from `data/starting_resources.toml` or runtime editing.
- The shipped Workbench supports manual buys for herbs, gem pieces, potion direct buys, and sold equipment/accessories, plus manual sells for ingredients, potions, gems, and standalone equipment instances.
- Ring and necklace socketing ships in the `Accessories` workbench tab; the inspector is read-only for combo details.

## How Dan Likes To Work

These notes are based on repo instructions and recent sessions. No project-specific prior chat logs were found in this repo when this README was written on March 8, 2026.

- Execute, do not just propose, unless the request is explicitly for planning or discussion.
- Keep docs synced with shipped reality in the same change. Do not leave roadmap or schema docs describing placeholder behavior after the code has moved on.
- Regenerate derived artifacts when schema or seed inputs change. In this repo that usually means `data/seed_scenario.json` and the embedded seed block in `index.html`.
- Verify with tests instead of stopping at code edits. Importer changes should be backed by importer tests; UI/runtime changes should be backed by smoke coverage.
- Use Playwright Chromium for screenshot-based visual QA. Do not fall back to Firefox.
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

- dedicated Base Inventory or Shop editors for `socketed_gems`

If a requested change crosses one of those boundaries, check the roadmap first and either:

- implement it intentionally and update the roadmap/docs/tests, or
- keep the change within the current phase boundary.

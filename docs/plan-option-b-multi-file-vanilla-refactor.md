# Plan: Option B Multi-File Vanilla Refactor

## Summary

This plan keeps Poshy framework-free and focuses on two outcomes:

- materially faster workbench and planner interactions,
- a maintainable multi-file source layout without changing the shipped scenario schema or user-facing behavior.

The source app will move out of the monolithic script in `index.html` into plain ES modules and CSS files. The release artifact will remain a single offline HTML file at `dist/index.html`.

Constraints for this plan:

- keep the persisted `v3` state schema and `localStorage` key unchanged,
- keep `data/seed_scenario.json` as the canonical generated scenario blob,
- keep the current visible UI and smoke-tested copy unless a test update is explicitly part of the change,
- do not adopt React, TypeScript compilation, or a planner worker in this option.

## Chosen Architecture

### Source entry and release artifact

- Keep repo-root `index.html` as the source shell.
- Replace the current inline app script with:
  - `<link rel="stylesheet" href="./src/styles.css">`
  - `<script type="module" src="./src/main.js"></script>`
- Keep the embedded seed block in repo-root `index.html` so local `file://` development and existing smoke flows still work.
- Add `scripts/build_single_file.mjs` to bundle `src/main.js`, inline the bundled JS and CSS into `dist/index.html`, and copy the current seed-data block into the built artifact.

### Exact source layout

- `src/main.js`
- `src/state/store.js`
- `src/state/selectors.js`
- `src/domain/validation.js`
- `src/domain/catalog.js`
- `src/domain/workbench.js`
- `src/domain/history.js`
- `src/domain/planner.js`
- `src/persistence/local-storage.js`
- `src/ui/render-root.js`
- `src/ui/chrome.js`
- `src/ui/inspector.js`
- `src/ui/toast.js`
- `src/ui/events.js`
- `src/ui/tabs/workbench.js`
- `src/ui/tabs/planner.js`
- `src/ui/tabs/inventory.js`
- `src/ui/tabs/shop.js`
- `src/ui/tabs/recipes.js`
- `src/ui/tabs/data.js`
- `src/styles.css`

### State model

- Keep persisted state shape exactly as:
  - `scenario`
  - `workbench`
  - `history`
  - `redo`
  - `planner`
- Move all transient browser-only UI into a non-persisted `uiState`.
- Add internal version counters in store metadata:
  - `scenarioVersion`
  - `workbenchVersion`
  - `historyVersion`
  - `plannerVersion`
  - `uiVersion`
- Every mutating store action must increment only the versions affected by that action.

### Rendering model

- Replace the current whole-app `renderApp()` approach with region rendering:
  - `renderChromeOnce()`
  - `renderActiveTab()`
  - `renderInspectorRegion()`
  - `renderToastRegion()`
- Only the active tab may render tab body markup.
- Hidden tabs must not be built into the DOM.
- Datalists and static chrome are rendered once per `scenarioVersion`, not once per interaction.
- Keep delegated event handling at the document level, but route each action to store mutations plus the minimum region rerender.

### Performance rules

- Memoize all derived view data in `src/state/selectors.js`, keyed by the relevant version counters.
- Precompute and cache search text for recipes, ingredients, equipment definitions, and equipment instances once per `scenarioVersion` or `workbenchVersion`.
- Debounce text filters and planner picker search by `100 ms`.
- Batch persistence with `queuePersist()` using `requestIdleCallback` and a `setTimeout(0)` fallback.
- Preserve scroll and focus only for regions that are actually rerendered.
- Keep planner compute on the main thread in this option, but remove repeated unnecessary cloning, re-sorting, and string building from the preview path.

## Implementation Phases

### Phase 1: Shell and module extraction

- Replace the inline runtime script in `index.html` with a module entry and stylesheet link.
- Move pure helpers first:
  - validation helpers,
  - catalog lookups,
  - formatting helpers,
  - workbench transaction helpers,
  - planner helpers.
- Add `// @ts-check` and JSDoc typedefs in every new source file.
- Keep function names stable where practical to reduce migration risk during extraction.

### Phase 2: Store and selector layer

- Create `src/state/store.js` as the only mutable state owner.
- Move all direct `state.* = ...` writes behind store actions.
- Create selector functions for:
  - workbench recipe entries,
  - holdings groups,
  - market rows,
  - inspector payloads,
  - planner goal normalization,
  - planner holdings view,
  - planner picker options,
  - run summary stats.
- Cache selector results by version counters so repeated same-state renders do not recompute the same arrays.

### Phase 3: Region-based UI

- Implement one renderer per major screen:
  - workbench,
  - planner,
  - inventory,
  - shop,
  - recipes,
  - data.
- Keep existing `data-action`, `data-*`, and role attributes unless a specific test update requires a change.
- Render inspector and toast separately from the tab body.
- Stop rebuilding inactive mobile sheets, hidden planners, and unused tab content on unrelated actions.

### Phase 4: Planner cleanup inside the vanilla architecture

- Keep planner API synchronous in this option:
  - `buildPlannerPreview(appState, normalizedGoals) -> PlannerPreview`
- Refactor planner code to use cached lookup tables from `catalog.js` instead of repeatedly scanning live scenario arrays.
- Replace repeated sorting of stable name lists with pre-sorted catalog arrays.
- Replace repeated `JSON.stringify`-based comparisons where a cheaper keyed representation is sufficient.
- Keep the current deterministic behavior and result ordering unchanged.

### Phase 5: Persistence and scroll/focus behavior

- Move `localStorage.setItem()` behind `queuePersist()`.
- Persist only after state changes that affect persisted slices.
- Do not persist on purely transient UI actions such as tab switches, picker open state, or mobile sheet visibility.
- Replace the current global scroll snapshot scan with per-region snapshot helpers:
  - active tab content,
  - visible inspector pane,
  - visible mobile sheet.

### Phase 6: Release build and docs

- Add `package.json` with only the build tooling needed for bundling and minification.
- Add `npm run build` that calls `node scripts/build_single_file.mjs`.
- Keep root `index.html` as the editable source shell and `dist/index.html` as the release artifact.
- Update docs to describe:
  - source layout,
  - build command,
  - the difference between source shell and release artifact.

## Public Interfaces And Compatibility

### Persisted compatibility

- Persisted saved-state shape stays unchanged.
- `localStorage` key remains `poshy.single-file.lab.v3`.
- `data/seed_scenario.json` and the embed script remain the canonical data pipeline.

### Internal interfaces introduced by this plan

- `createStore(initialState)`
- `dispatch(action)`
- `queuePersist(reason)`
- `selectWorkbenchView(state)`
- `selectPlannerView(state)`
- `buildPlannerPreview(state, normalizedGoals)`

### Non-changes

- No server.
- No routing layer.
- No framework runtime.
- No worker-based planner execution.

## Test Plan And Acceptance Criteria

### Keep existing coverage

- `tests/test_import_workbook.py`
- `tests/test_embed_seed_data.py`
- `tests/test_index_smoke.py`

### Add coverage

- Add a build verification test that opens `dist/index.html` and confirms the seed block, startup shell, and one planner preview all work in the release artifact.
- Add unit-level browserless tests for selectors that are expected to memoize and preserve sorting behavior.

### Acceptance criteria

- Current smoke tests still pass with equivalent visible behavior.
- Startup stays within `10%` of the current baseline.
- The following smoke checkpoints improve by at least `30%`:
  - `configure and preview mixed cross-system planner goal`
  - `validate planner scope filters preserve selection`
  - `inspect workbench categories and holdings detail`
- Actions that affect only the active tab no longer rebuild hidden tabs.
- Pure UI actions no longer trigger full persisted-state writes.

## Assumptions

- Offline single-file distribution remains required for release builds.
- Root `index.html` may become a source shell, but it must stay usable for local `file://` development.
- This option intentionally optimizes the existing architecture before taking on framework migration cost.

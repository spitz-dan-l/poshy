# Plan: Option D React + TypeScript + Vite Rewrite

## Summary

This plan rewrites Poshy as a typed React application with Vite while preserving the current offline product model and runtime behavior.

Primary goals:

- eliminate whole-app rerenders and hidden-tab work,
- move heavy planner preview work off the main UI thread,
- make future changes safer by introducing typed boundaries between domain logic, state, and UI.

Constraints for this plan:

- keep the persisted `v3` state schema and `localStorage` key unchanged,
- keep `data/seed_scenario.json` and the workbook import pipeline as source of truth,
- preserve current visible behavior, DOM semantics, and smoke-tested flows unless a specific update is necessary and done in the same change,
- ship a single offline `dist/index.html` release artifact even though source code becomes a normal Vite app.

## Chosen Stack

- React with TypeScript in strict mode.
- Vite as the app build tool and dev server.
- Zustand for application state with selector-based subscriptions.
- Vitest for unit tests.
- React Testing Library for component-level behavior tests.
- Playwright smoke tests retained for end-to-end parity.
- Plain CSS files imported by feature; no CSS-in-JS.
- Planner preview executed in an inlined worker created from a dedicated TypeScript module and instantiated through a Blob-backed URL during runtime.

## Chosen Architecture

### Source layout

- `src/main.tsx`
- `src/app/App.tsx`
- `src/app/store.ts`
- `src/app/persist.ts`
- `src/app/bootstrap.ts`
- `src/types/scenario.ts`
- `src/types/state.ts`
- `src/types/planner.ts`
- `src/domain/validation.ts`
- `src/domain/catalog.ts`
- `src/domain/workbench.ts`
- `src/domain/history.ts`
- `src/domain/planner-core.ts`
- `src/planner/worker.ts`
- `src/planner/client.ts`
- `src/components/chrome/`
- `src/components/inspector/`
- `src/components/toast/`
- `src/features/workbench/`
- `src/features/planner/`
- `src/features/inventory/`
- `src/features/shop/`
- `src/features/recipes/`
- `src/features/data/`
- `src/styles/tokens.css`
- `src/styles/app.css`

### HTML shell and seed data

- Keep repo-root `index.html` as the Vite HTML entry.
- Remove the checked-in embedded seed block from source `index.html` and replace it with a stable mount shell plus a Vite-owned seed placeholder comment.
- Add a custom Vite plugin using `transformIndexHtml` that:
  - reads `data/seed_scenario.json`,
  - injects `<script id="seed-data" type="application/json">...</script>` into HTML during dev and build,
  - invalidates and reloads when the JSON changes.
- `src/app/bootstrap.ts` reads the injected seed JSON from the DOM on startup and validates it before creating the store.
- Add a postbuild step that inlines emitted JS and CSS into `dist/index.html` so the release artifact remains one offline file.
- Retire `scripts/embed_seed_data.py` from the normal app build path for this option.
- Treat `dist/index.html` as the real offline artifact; source `index.html` is now a Vite entry file, not a directly distributed standalone app.

### State model

- Persisted state remains:
  - `scenario`
  - `workbench`
  - `history`
  - `redo`
  - `planner`
- UI-only state lives outside the persisted payload:
  - active tab,
  - filters,
  - selected inspector item,
  - mobile sheet state,
  - planner picker open/query state,
  - toast state.
- Zustand store is split into slices:
  - `scenarioSlice`
  - `workbenchSlice`
  - `plannerSlice`
  - `historySlice`
  - `uiSlice`
  - `persistSlice`
- Every selector used by components must subscribe to the narrowest possible slice to avoid broad rerenders.

### Planner worker boundary

- All planner preview computation moves into `src/planner/worker.ts`.
- Main thread code in `src/planner/client.ts` owns request lifecycle, cancellation, and stale-result rejection.
- Worker request type:
  - `PreviewPlanRequest { requestId, persistedState, normalizedGoals }`
- Worker response type:
  - `PreviewPlanResult { requestId, preview, metrics }`
  - `PreviewPlanError { requestId, message }`
- `metrics` must include:
  - `solveMs`
  - `fundingMs`
  - `previewMaterializeMs`
  - `totalMs`
- The main thread adopts worker results only when `requestId` matches the latest requested preview.

### React rendering rules

- Only the active tab tree is mounted.
- Inspector, toast zone, and active mobile sheet are separate top-level regions.
- Use `startTransition` when committing large planner preview results and tab-level filter updates.
- Use `useDeferredValue` for high-frequency text filters and planner picker search.
- Use `useEffectEvent` for event handlers that need current store state without triggering unnecessary effect resubscription.
- Keep derived domain calculations out of React components; components only consume typed selectors and action creators.

## Implementation Phases

### Phase 1: Scaffold and shell

- Add Vite, React, TypeScript, Vitest, and React Testing Library.
- Replace the current inline app code in `index.html` with a React mount node and module entry.
- Remove the checked-in seed-data block from source `index.html` but keep the footer copy and HTML shell structure.
- Add `vite.config.ts`, the custom HTML seed-injection plugin, and a postbuild script that inlines final JS and CSS into `dist/index.html`.

### Phase 2: Extract and type the domain model

- Move validation, catalog, workbench transaction logic, history replay, and planner core into `src/domain/`.
- Introduce explicit TypeScript types for:
  - `Scenario`
  - `WorkbenchState`
  - `PlannerState`
  - `PersistedState`
  - `HistoryEntry`
  - `PlannerGoalLine`
  - `PlannerPreview`
- Preserve current runtime validation behavior and current persisted schema exactly.

### Phase 3: Zustand store and persistence

- Implement one Zustand store with typed slices and exported selectors.
- Add a persistence queue that writes only the persisted slices to `localStorage`.
- Keep the key as `poshy.single-file.lab.v3`.
- Do not persist transient UI state.
- Recreate current reset, undo, redo, import, and apply-plan behavior through store actions rather than direct mutation.

### Phase 4: Feature migration to React components

- Rebuild the app as feature components without changing feature behavior:
  - workbench
  - planner
  - inventory
  - shop
  - recipes
  - data/import-export
- Preserve current `data-action`, `data-*`, and role attributes wherever practical so Playwright selectors continue to work.
- Keep the current visual design system by porting the CSS variables and existing class naming patterns into `src/styles/`.

### Phase 5: Planner worker migration

- Move `buildPlannerPreview` off the main thread into the worker.
- Keep goal normalization and local UI validation on the main thread so validation feedback remains immediate.
- Keep planner preview deterministic and ordered exactly as today.
- Report worker metrics back to the main thread and expose them through `performance.mark()` instrumentation for test and profiling use.
- If a newer preview request supersedes an older one, discard the older result without mutating UI state.

### Phase 6: Test migration, parity, and release packaging

- Port unit-like logic tests to Vitest where they do not need a browser.
- Keep Playwright smoke coverage for full end-to-end parity.
- Update smoke runs to target the built release artifact at `dist/index.html`.
- Add one smoke run against a Vite-served dev build to catch source-only issues before packaging.
- Update docs to explain:
  - the new source tree,
  - Vite development flow,
  - Vite-owned seed injection from `data/seed_scenario.json`,
  - release build and single-file packaging,
  - the unchanged canonical workbook import pipeline.

## Public Interfaces And Compatibility

### Persisted compatibility

- Persisted state schema remains unchanged.
- `localStorage` key remains `poshy.single-file.lab.v3`.
- `data/seed_scenario.json` stays canonical.
- `scripts/import_workbook.py` remains the canonical generator.
- `scripts/embed_seed_data.py` is no longer part of the main app build path in this option.

### New internal interfaces

- `createAppStore(initialState: PersistedState): AppStore`
- `queuePersist(): void`
- `requestPlannerPreview(normalizedGoals: PlannerGoals): Promise<void>`
- `buildPlannerPreview(state: PersistedState, goals: PlannerGoals): PlannerPreview`
- `PreviewPlanRequest`
- `PreviewPlanResult`
- `PreviewPlanError`

### Non-changes

- No backend or API server.
- No React Router.
- No schema migration for existing saved data.
- No intentional redesign of the product UI.

## Test Plan And Acceptance Criteria

### Required test coverage

- Keep:
  - `tests/test_import_workbook.py`
  - `tests/test_embed_seed_data.py`
  - Playwright smoke coverage for end-to-end behavior
- Add:
  - Vitest tests for validation, workbench transaction replay, and planner-core helpers
  - React Testing Library tests for tab rendering, inspector updates, and planner UI state flows
  - worker tests for stale request rejection and deterministic preview responses

### Acceptance criteria

- Current smoke behavior remains equivalent from the user’s perspective.
- The slowest planner checkpoint, `configure and preview mixed cross-system planner goal`, improves by at least `40%`.
- Tab switches, filter edits, and inspector changes do not render inactive tabs.
- Planner preview no longer blocks typing or tab interaction while computation is in progress.
- Release build remains a single offline `dist/index.html` file containing the embedded seed data.
- Vite dev mode serves HTML with the same injected seed data that the release build contains.

## Assumptions

- Offline single-file distribution remains required for release builds even after moving to React and Vite.
- Source `index.html` no longer needs to be directly runnable over `file://`; the offline deliverable is the built `dist/index.html`.
- The React rewrite is justified only if Poshy will continue growing beyond the current phase-6 scope.
- This option is intentionally higher-cost than Option B and should only be chosen if the team wants both performance gains and a long-term typed UI architecture.

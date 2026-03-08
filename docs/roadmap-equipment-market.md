# Roadmap: Full Equipment Market With Ring/Necklace Gem Combos

## Summary

- Better factoring still applies: build one shared economy/simulator foundation first, then layer equipment, combo assembly, selling, and finally the planner on top.
- Full combo scope now includes synthesized ring and necklace accessory+gem combinations, not just stored interaction hooks.
- Recommended delivery order:
  1. Economy/state/action foundation.
  2. Equipment importer and catalog expansion.
  3. Ring/necklace combo assembly and disassembly.
  4. Selling across ingredients, outputs, equipment, and assembled combos.
  5. Planner tab with exact optimization over all supported actions.

## Phase Breakdown

### Phase 1: Economy and State Foundation

Goal:
- Create the data model and runtime plumbing that every later phase depends on.

Changes:
- Extend the canonical scenario with `equipment`, `market`, and `for_sale.equipment`.
- Extend base inventory and workbench state with `equipment` as unique instances rather than counter maps.
- Replace the current narrow `effect` payload with a generic transaction list that can represent buy, sell, craft, assemble, disassemble, and equipment-instance mutations.
- Add a pure runtime simulator in `index.html` that owns all workbench mutations and can be called by manual actions, undo/redo, and the future planner.
- Add market-value helpers for stackables and equipment so later phases reuse one pricing path.

Deliverables:
- Scenario validation accepts the expanded shape.
- Persisted state validation accepts the new workbench and history shape.
- Existing manual `craft once`, `buy once`, undo, redo, and persistence flows run through the new simulator instead of directly mutating state.
- Saved-state validation rejects legacy history/effect payloads cleanly.

Out of scope:
- No equipment importer yet.
- No equipment UI yet.
- No selling yet.
- No planner yet.

Done means:
- Existing potion/gem workbench behavior still works after the refactor.
- The browser can load, persist, undo, and redo using the new simulator/effect model.

### Phase 2: Equipment Import and Catalog Surfacing

Goal:
- Ingest equipment from the workbook and make it visible/editable in the scenario/runtime without combo behavior yet.

Changes:
- Import equipment from all gear-like workbook sheets plus `Accessories`.
- Normalize workbook rows into a single catalog shape with `name`, `family`, `source_sheet`, `rank`, `buy_price`, `max_hp | null`, `stats`, `effects`, `optimizer_auto_sell`, and optional `socket_policy`.
- Parse `Accessories` in multiple passes:
  - Preserve the current gem metadata extraction.
  - Add standalone shield and talisman equipment definitions.
  - Add socketable base definitions for rings and necklaces.
- Extend the seed scenario JSON and embedded seed block to include equipment catalog data and equipment inventory.
- Add base inventory editor support for equipment instances, including current HP and `optimizer_auto_sell`.

Deliverables:
- Importer emits a stable `equipment` section in the scenario.
- Equipment appears in runtime validation and survives reload/persistence.
- Inventory/base editor can display and edit equipment instances.
- No manual workbench actions depend on combos yet.

Out of scope:
- No buy/sell equipment actions yet.
- No combo assembly/disassembly yet.
- No planner yet.

Done means:
- Workbook-derived equipment exists in the scenario and browser state with no manual JSON patching.
- Ring and necklace bases are present as equipment catalog entries, but not yet combinatorial instances.

### Phase 3: Manual Equipment Market

Goal:
- Make standalone equipment participate in the workbench economy before introducing combos.

Changes:
- Add manual workbench actions for `buy equipment` and `sell equipment`.
- Buying equipment creates full-HP equipment instances from catalog entries.
- Selling equipment uses HP-aware valuation when `max_hp` exists.
- Keep `for_sale` as buy-side availability only; selling is allowed for any priced owned item.
- Surface equipment in the workbench holdings, inspector, action log, and toasts.
- Add `for_sale.equipment` editor controls and UI visibility in the shop tab.

Deliverables:
- Users can buy standalone equipment from the shop.
- Users can sell owned standalone equipment from holdings/workbench.
- Undo/redo and persisted history work for equipment transactions.

Out of scope:
- No ring/necklace combo assembly yet.
- No stackable selling yet unless needed to unify the sell UI.
- No planner yet.

Done means:
- Standalone equipment behaves as a first-class manual economy entity in the browser.

### Phase 4: Ring/Necklace Combo Assembly and Disassembly

Goal:
- Add the full accessory/gem combination system for rings and necklaces.

Changes:
- Model assembled accessories as equipment instances with `base_name`, `socketed_gems`, `current_hp | null`, and a canonical display label.
- Normalize `socketed_gems` as a sorted multiset so duplicate gems are allowed but the same combo has one canonical representation.
- Treat rings as socketable bases with `min_gems = 0`, `max_gems = 1`, `imbue_fee = 50`, and workbook buy price `40`.
- Treat necklaces as socketable bases with `min_gems = 1`, `max_gems = 3`, `imbue_fee = 50` per inserted gem, and workbook buy price `150`.
- Add manual actions for `assemble accessory` and `disassemble accessory`.
- Combo assembly consumes one owned base accessory instance plus owned gem outputs; if only gem pieces are owned, the user must first obtain gem outputs through existing craft/buy flows.
- Disassembly is free and returns the exact base accessory instance plus embedded gem outputs.
- Compute assembled combo sell value as the sum of component sell values of the base accessory plus embedded gems; imbuement fees are sunk.

Deliverables:
- Users can build ring combos and necklace combos manually.
- Users can disassemble combos back into components.
- Combo instances display correctly in holdings, inspector, history, and persistence.
- Selling an assembled combo is value-equivalent to disassemble-then-sell.

Out of scope:
- Shields and talismans remain standalone.
- No planner yet.

Done means:
- Full manual combo lifecycle exists: acquire parts, assemble, inspect, sell, disassemble, undo, redo, reload.

### Phase 5: Selling for Ingredients and Outputs

Goal:
- Complete the sell-side economy for the existing stackable item types.

Changes:
- Add manual sell actions for ingredients, potion outputs, and gem outputs.
- Use one shared market-value helper for stackable sell values.
- If an output has no direct buy price, derive its market value from its recipe input prices.
- Surface sell actions from holdings/workbench and record them through the same simulator/effect path as all other actions.

Deliverables:
- Users can manually sell any owned ingredient or output.
- Manual sell flows work alongside equipment and combo selling.
- Undo/redo and persistence are stable across mixed craft/buy/sell/combo histories.

Out of scope:
- No planner yet.

Done means:
- All manual economy actions are implemented before optimization starts.

### Phase 6: Planner Tab and Optimization

Goal:
- Add a new planning surface that computes minimum-net-cost action sequences using the already-built simulator.

Changes:
- Add a Planner tab where request lines can ask to buy or sell stackables, buy or sell equipment instances, and assemble or disassemble specific ring/necklace combos.
- Keep the objective as `minimum net gold cost` while exactly satisfying requested actions.
- Allow the planner to:
  - Auto-buy ingredients.
  - Choose craft-vs-buy for outputs.
  - Buy or craft gems for combo assembly.
  - Disassemble combos when useful.
  - Auto-sell ingredients and outputs freely.
  - Auto-sell only equipment whose catalog entry is tagged `optimizer_auto_sell`.
- Implement the solver as a deterministic memoized branch-and-bound search over normalized simulator state plus remaining request lines.
- Reuse the simulator for plan preview and plan application so planner behavior matches manual action behavior.

Deliverables:
- Users can create requests, preview an optimized plan, and apply it to the workbench.
- Planner output uses the same canonical combo representation as manual assembly.
- Planner can reason over stackables, standalone equipment, and ring/necklace combos together.

Out of scope:
- No additional accessory families beyond rings and necklaces.
- No alternative optimizer objective in this phase.

Done means:
- The planner produces deterministic, explainable plans and those plans replay correctly in the workbench/history system.

## Key Changes

- Extend the canonical scenario with `equipment`, `market`, and `for_sale.equipment`, and extend workbench/base inventory with `equipment` as unique instances rather than counters.
- Replace the current narrow `effect` payload with a generic transaction list that can represent buy, sell, craft, assemble, disassemble, and equipment-instance mutations while keeping `before`/`after` snapshots for undo/redo.
- Add a pure runtime simulator in `index.html` that owns every inventory mutation; UI handlers and planner execution both call that simulator.
- Import equipment from all gear-like workbook sheets plus `Accessories`; normalize each sheet family into one catalog shape with `name`, `family`, `source_sheet`, `rank`, `buy_price`, `max_hp | null`, `stats`, `effects`, `optimizer_auto_sell`, and optional `socket_policy`.
- Parse `Accessories` in multiple passes: keep the existing gem metadata extraction, add standalone shield/talisman equipment definitions, and add socketable accessory definitions for rings and necklaces.
- Model assembled accessories as equipment instances with `base_name`, `socketed_gems`, `current_hp | null`, and a canonical display label; normalize `socketed_gems` as a sorted multiset so duplicate gems are allowed but identity is deterministic.
- Treat rings as socketable bases with `min_gems = 0`, `max_gems = 1`, `imbue_fee = 50`, and workbook buy price `40`.
- Treat necklaces as socketable bases with `min_gems = 1`, `max_gems = 3`, `imbue_fee = 50` per inserted gem, and workbook buy price `150`; direct market purchase of a new necklace requires at least one gem, but disassembly may leave a bare necklace in inventory.
- Keep shields and talismans as standalone equipment in this roadmap; no synthesized gem combinations for them.
- Add manual workbench actions for `buy equipment`, `sell equipment`, `assemble accessory`, and `disassemble accessory`, alongside the existing craft/buy output flows.
- Combo assembly uses owned base accessory instances plus owned gem outputs; if the user only has gem pieces, existing gem crafting/buy logic is used first to obtain the gem output item.
- Disassembly is free and returns the exact base accessory instance plus the embedded gem outputs back to inventory.
- Selling remains available for any priced item, independent of weekly `for_sale` flags; `for_sale` is buy-side availability only.
- Compute ingredient and output sell value from a shared market-value helper using the configured markdown; if an output has no direct buy price, derive its market value from its recipe input prices.
- Compute standalone equipment sell value from buy price and remaining HP when HP exists.
- Compute assembled ring/necklace sell value as the sum of component sell values of the base accessory plus embedded gems; imbuement fees are sunk and contribute no resale value, so `disassemble then sell` equals `sell assembled`.
- Add a new Planner tab where request lines can ask to buy or sell stackables, buy or sell equipment instances, and assemble or disassemble specific ring/necklace combos.
- Planner objective stays `minimum net gold cost` while exactly satisfying the requested actions.
- Planner may auto-buy ingredients, choose craft-vs-buy for outputs, buy/craft gems for combo assembly, disassemble combos, auto-sell ingredients and outputs freely, and auto-sell only equipment whose catalog entry is tagged `optimizer_auto_sell`.
- Implement the planner as a deterministic memoized branch-and-bound search over normalized simulator state plus remaining request lines; combo state keys use canonical base accessory plus sorted gem multiset.

## Suggested Phase Order

- Build Phase 1 first and do not start later UI or optimizer work before the simulator and state model are stable.
- Build Phase 2 next so all later phases target the real equipment catalog rather than temporary mock data.
- Build Phase 3 before Phase 4 so standalone equipment buy/sell behavior is settled before combo-specific logic lands.
- Build Phase 4 before Phase 5 if combo-specific selling is easier to validate while only equipment selling exists.
- Build Phase 5 before Phase 6 so the planner is the last consumer of a complete manual action set, not the place where missing market logic gets invented.

## Public Interfaces and Types

- `Scenario.inventory` gains `equipment`.
- `Scenario.for_sale` gains `equipment`.
- `Scenario` gains `market` and `equipment`.
- Add persisted `EquipmentDefinition` and `EquipmentInstance` types.
- Represent assembled accessories as `EquipmentInstance`, not as separate recipe/output records.
- `HistoryEntry.effect` becomes a generic transaction schema and saved-state validation should reject legacy effect payloads.

## Test Plan

- Importer tests for each equipment family plus dual-pass `Accessories` parsing.
- Validation tests for malformed equipment definitions, malformed equipment instances, invalid socket policies, and stale saved-state history entries.
- Browser smoke tests for buying standalone equipment, assembling a ring combo, assembling a necklace combo with repeated gems, disassembling combos, selling assembled combos, undo/redo, and persistence across reload.
- Planner tests for gem crafting before combo assembly, craft-vs-buy choice for gem acquisition, disassembly as an intermediate step, equipment auto-sell tag enforcement, and exact fulfillment of requested combo actions.

## Assumptions

- Full combo scope for this roadmap means rings and necklaces only; shields and talismans stay standalone.
- Duplicate gems in one combo are allowed.
- Assembled combos are not separate shop stock; they are created from components.
- Workbook literal prices are authoritative for accessory buying.
- Imbuement fee is always paid on assembly, never recovered on sell, and disassembly is free.
- Bare necklaces may exist only after disassembly or seed/import data, not as a direct new shop purchase state.

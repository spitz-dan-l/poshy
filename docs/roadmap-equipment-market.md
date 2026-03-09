# Roadmap: Full Equipment Market With Ring/Necklace Gem Combos

## Summary

This roadmap now reflects shipped work through phase 5 as of March 9, 2026.

Recommended delivery order remains:

1. Economy and state foundation.
2. Equipment import and catalog surfacing.
3. Manual equipment market actions.
4. Ring and necklace combo assembly/disassembly.
5. Selling for ingredients and outputs.
6. Planner and optimization.

Current status:

- Phase 1 is implemented.
- Phase 2 is implemented.
- Phase 3 is implemented.
- The post-phase-3 UI passes are implemented.
- Phase 4 is implemented.
- Phase 5 is implemented.
- Phase 6 is still future work.

## Phase Breakdown

### Phase 1: Economy And State Foundation

Status:

- Implemented on March 8, 2026.

Shipped scope:

- Extended the canonical scenario with `market`, `equipment`, and `for_sale.equipment`.
- Extended base inventory and workbench state with `equipment` as unique instances instead of counters.
- Replaced the old narrow effect payload with transaction-based history entries.
- Moved manual craft, buy, undo, redo, and persistence flows onto the shared simulator path in `index.html`.
- Added strict runtime validation for scenario data, workbench state, and saved history.

Done means:

- potion and gem workbench behavior still works through the new simulator,
- runtime sell-value helpers already exist,
- saved-state validation rejects legacy history payloads,
- phase 2 could build on real equipment-aware state instead of adding another migration later.

### Phase 2: Equipment Import And Catalog Surfacing

Status:

- Implemented on March 8, 2026.

Shipped scope:

- Import equipment definitions from:
  - `Axes&Spears`
  - `Swords&Bows`
  - `Staves&Orbs`
  - `Runestones`
  - `Light&Heavy `
  - `Robe&Hide`
  - `Golem&Gauntlet`
  - `Headware`
  - `Familiars`
  - `Footwear`
  - `Mounts&Legs`
  - `Accessories`
- Preserve gem metadata import from `Accessories` and add accessory parsing for:
  - ring bases,
  - necklace bases,
  - shield definitions,
  - talisman definitions.
- Emit workbook-derived `equipment.definitions` with:
  - `name`
  - `family`
  - `category`
  - `rank`
  - `buy_price`
  - `max_hp`
  - `stats`
  - `effects`
  - optional `socket_policy`
- Normalize imported equipment `rank` values to the leading workbook tier letter.
- Emit `socket_policy` only for rings and necklaces.
- Extend `data/starting_resources.toml` so it can author:
  - `[[inventory.equipment]]`
  - `[for_sale.equipment]`
- Regenerate `data/seed_scenario.json` and sync the embedded seed block in `index.html`.
- Surface equipment in the browser as:
  - read-only workbench holdings visibility,
  - equipment counts in run summary stats,
  - editable Base Inventory equipment instances,
  - Catalog visibility for imported equipment definitions.

Actual shipped constraints:

- no shop-tab editor for `for_sale.equipment` yet,
- no manual equipment buy/sell actions yet,
- no ring/necklace combo assembly yet,
- no socket editing yet.

Done means:

- workbook-derived equipment exists in canonical scenario data without manual JSON patching,
- base inventory can author standalone equipment instances,
- workbench visibly carries equipment state,
- catalog exposes imported equipment definitions,
- docs, seed JSON, embedded seed JSON, and tests all match the shipped phase-2 behavior.

### Phase 3: Manual Equipment Market

Status:

- Implemented on March 9, 2026.

Goal:

- Make standalone equipment participate in manual economy actions.

Shipped scope:

- add manual `buy equipment` and `sell equipment` actions,
- use full-HP creation on purchase,
- use HP-aware valuation on sell,
- add shop-tab controls for `for_sale.equipment`,
- surface equipment buy/sell actions in holdings, history, toasts, and undo/redo.

Done means:

- standalone equipment can be bought from the Workbench when its definition is sold this week,
- owned equipment can be sold per instance from Current Holdings,
- equipment sales use HP-aware gold gain and can produce fractional runtime gold,
- Shop can edit weekly `for_sale.equipment` flags and the Workbench market updates immediately,
- history, toasts, undo, redo, persistence, docs, and browser tests all reflect equipment market actions.

### Post-Phase-3 UI Pass: Category Tabs, Generic Inspector, And Ingredient Buys

Status:

- Implemented on March 8, 2026.

Goal:

- Make the shipped manual economy easier to browse by item class and close the inspector gap for non-recipe items.

Shipped scope:

- split the Workbench center panel into `Potions`, `Gems`, `Herbs`, `Gem Pieces`, `Equipment`, and `Accessories`,
- treat imported `category = "accessory"` as the source of truth for Workbench and holdings grouping,
- generalize the inspector so it can render:
  - potion outputs,
  - gem outputs,
  - herb and gem-piece ingredients,
  - equipment definitions,
  - owned equipment instances,
- add manual buy actions for herbs and gem pieces in the Workbench,
- split holdings gear rows into `Equipment` and `Accessories`,
- move most inline gear detail out of holdings/workbench tables and into the inspector,
- extend action-log inspect links beyond output recipes.

Done means:

- Workbench no longer mixes recipes, ingredients, and gear in one central list,
- herbs and gem pieces can be bought directly from the Workbench when sold this week,
- every item class visible in holdings, Workbench, or history can be inspected,
- accessory grouping is driven by imported `category` instead of a workbook-sheet check or hand-maintained family list,
- docs and browser tests reflect the shipped UI.

### Phase 4: Ring And Necklace Combo Assembly

Status:

- Implemented on March 8, 2026.

Goal:

- Add the accessory-plus-gem combo lifecycle for rings and necklaces only.

Shipped scope:

- model assembled accessories as runtime `EquipmentInstance` values with `socketed_gems`,
- add workbench-driven assemble and disassemble actions for owned rings and necklaces in the `Accessories` tab,
- consume owned gem outputs when assembling and return them on disassembly,
- charge the imported `imbue_fee` on assembly and never refund it,
- preserve the same accessory instance `id`, `base_name`, and `current_hp` across combo updates,
- compute assembled sell value as `sell(base accessory) + sell(each socketed gem)`,
- tighten runtime validation so `socketed_gems` is only valid on items with `socket_policy` and must contain `1..max_gems`,
- surface combo state in holdings cards, item inspector details, history inspect links, and undo/redo,
- remove visible equipment ids from shipped browser surfaces and keep them internal-only,
- keep the inspector read-only for accessories while still showing current sockets and sell breakdowns.

Done means:

- owned rings and necklaces can be assembled from owned gems without adding new scenario fields or transaction kinds,
- disassembly returns the exact gem outputs and keeps the same accessory instance identity,
- selling an assembled combo pays component sell value only and does not recover imbue fees,
- saved browser state, exported/imported scenario JSON, and `Set Base From Workbench` can all persist preassembled combos,
- docs and browser tests cover combo assembly, disassembly, undo/redo, and strict validation.

Explicit non-goals:

- shields stay standalone,
- talismans stay standalone.

### Phase 5: Selling For Ingredients And Outputs

Status:

- Implemented on March 9, 2026.

Goal:

- Finish sell-side manual market coverage for stackable items.

Shipped scope:

- add manual sell actions for ingredients,
- add manual sell actions for potion outputs,
- add manual sell actions for gem outputs,
- reuse one shared value helper for all stackable sell flows,
- keep behavior consistent with existing transaction-based history and undo/redo,
- surface stackable sell values and sell actions in Current Holdings,
- add sell-value details for ingredients, potions, and gems in the inspector,
- keep mobile holdings usable by collapsing stackable rows into labeled two-column cards at narrow widths.

Done means:

- owned herbs, gem pieces, potions, and gems can be sold one unit at a time from Current Holdings,
- stackable sells use the same persisted `stackable` transaction shape plus gold transactions instead of a new history schema,
- potion sell value still prefers direct buy price when present and otherwise falls back to recipe input cost,
- gem sell value still uses recipe input cost,
- history, toasts, inspect links, undo, redo, persistence, docs, and browser tests all reflect stackable sell actions.

### Phase 6: Planner And Optimization

Status:

- Not started.

Goal:

- Add a player-owned planner surface that computes exact minimum-net-cost sequences over the shipped manual action set.

Planned scope:

- request lines for:
  - `Stackable`: target output plus quantity,
  - `Equipment`: target standalone equipment plus quantity,
  - `Combo`: one socketable accessory plus explicit gem slots;
- a dedicated `Planner Rules` surface inside the planner tab, not in Catalog;
- deterministic solver over normalized simulator state for buy, sell, craft, assemble, and disassemble actions;
- craft-vs-buy choice for outputs and gem acquisition for combo assembly;
- liquidation only as a fallback funding mechanism when a valid plan is otherwise short on gold;
- plan preview and plan apply through the same simulator path as manual actions.

Planner UX:

- Insert `Planner` immediately after `Workbench` in the top-level tab row.
- Desktop planner layout should expose three areas:
  - goal builder,
  - plan preview,
  - `Rules`.
- Mobile planner layout should expose planner-specific section buttons:
  - `Goals`,
  - `Plan`,
  - `Rules`.
- Plan preview should stay deterministic and auditable:
  - status banner,
  - ordered step list,
  - funding section when liquidation is used,
  - summary metrics for gross spend, liquidation recovered, net gold delta, and steps.
- `Apply Plan` should expand the normalized preview back into ordinary simulator transactions and ordinary action-log rows. Planner rule edits themselves are not history entries.

Planner Rules:

- Delete the obsolete `optimizer_auto_sell` field from the canonical equipment definition schema and do not support it in scenario import JSON.
- Sell permissions are player-owned per-run planner state, not scenario/admin metadata.
- Rules should be split into two explicit groups:
  - `Equipment Sell Permissions`: allow or protect owned equipment instances from planner liquidation;
  - `Ingredient Reserves`: keep floors for herbs and gem pieces plus pinned output reserves such as “keep enough for Blessed medicine x1”.
- The planner should surface liquidation reasons in player language:
  - needed for this plan,
  - reserved for pinned crafts,
  - kept because of your floor.

Persistence:

- Add planner state outside `Scenario`, stored alongside `workbench`, `history`, and `redo`.
- Minimum planner state shape:
  - `sellable_equipment_ids: Record<string, true>`
  - `ingredient_keep_counts: Record<string, number>`
  - `pinned_output_reserves: Record<string, number>`
- Planner state persists with the current run, resets with `Reset Run` and `Seed From Base`, and is ignored by undo/redo.
- When phase 6 lands, bump the browser storage key so old local saved runs are ignored instead of failing to load against the stricter schema.

Liquidation Policy:

- The planner should first solve without liquidation.
- Only enter liquidation mode when the best non-liquidation plan has a gold shortfall.
- V1 automatic liquidation candidates:
  - owned equipment instances explicitly approved in planner rules,
  - herbs and gem pieces above their protected counts.
- V1 non-candidates:
  - potion outputs,
  - gem outputs,
  - any ingredient units protected by current-goal needs, pinned reserves, or keep floors.
- Protected ingredient count should cover:
  - current planner goals,
  - pinned output reserves,
  - explicit player keep floors.
- Candidate selection must be deterministic and reviewable. Prefer:
  - larger surplus above protection,
  - lower recipe fan-out,
  - higher immediate gold value,
  - alphabetical tie-breaker.
- The planner should sell only enough allowed inventory to cover the shortfall.
- If funding still fails, the blocked state should report:
  - remaining shortfall,
  - which protection rule prevented more selling,
  - the highest-value remaining protected candidates when that helps explain the failure.

## Current Baseline For Future Phases

Future work should assume these facts are already true:

- `equipment.definitions` is populated from the workbook and currently contains real catalog data.
- `inventory.equipment` and `for_sale.equipment` already exist in canonical scenario JSON.
- standalone equipment instances are already editable in Base Inventory.
- Workbench uses category tabs for outputs, ingredients, equipment, and accessories.
- Workbench holdings split standalone gear into `Equipment` and `Accessories` using compact cards without visible instance ids.
- Workbench exposes manual herb and gem-piece buys plus the existing manual equipment market driven by `for_sale.equipment`.
- workbench holdings expose per-unit stackable sell controls, per-instance equipment sell controls, and summary stats expose equipment counts.
- Shop exposes weekly equipment sale toggles.
- Catalog already exposes imported equipment definitions as read-only reference data.
- rings and necklaces already exist as base definitions with socket policy metadata.
- ring and necklace combos can be assembled and disassembled in the `Accessories` workbench tab using owned gems.
- `socketed_gems` can now appear on persisted ring and necklace instances, including base state copied from the workbench.
- holdings and history already understand equipment `update` transactions for combo lifecycle actions.
- Base Inventory still does not provide a dedicated socket editor and no longer shows visible instance ids.

## Public Interfaces Already Shipped

- `Scenario.market = { sell_markdown: number }`
- `Scenario.equipment = { definitions: Record<string, EquipmentDefinition> }`
- `Scenario.inventory.equipment: EquipmentInstance[]`
- `Scenario.for_sale.equipment: Record<string, true>`
- `EquipmentInstance.socketed_gems?: string[]`
- transaction-based `HistoryEntry.effect.transactions`

## Remaining Test Plan

Future phases should extend the current shipped coverage with:

- schema and import tests that reject the removed `optimizer_auto_sell` field;
- planner-state persistence tests for defaulting, reset, and storage-key rollover;
- planner-rule tests covering:
  - approved equipment liquidation,
  - protected equipment,
  - herb and gem-piece keep floors,
  - pinned output reserves,
  - current-goal inputs never being sold away;
- funding behavior tests covering:
  - liquidation only after a non-liquidation shortfall,
  - deterministic ingredient candidate ranking,
  - selling only enough allowed inventory to cover the gap,
  - blocked plans that report the remaining shortfall and the limiting rules;
- planner tests over mixed stackable, equipment, and combo requests.

## Assumptions

- Full combo scope for this roadmap still means rings and necklaces only.
- Duplicate gems inside one combo are allowed.
- Assembled combos are created from components, not imported as separate shop stock.
- Imbue fees remain sunk costs and are not recovered on resale.
- No backward compatibility is planned for `optimizer_auto_sell` in scenario/import data.
- Planner sell permissions are player-owned and persist per run.
- V1 automatic liquidation covers approved equipment plus herbs and gem pieces only.
- Manual herb and gem-piece buys shipped before the rest of the stackable sell-side phase.

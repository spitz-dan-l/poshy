# Phase 6 Planner Walkthroughs

Use this alongside [phase6-planner-mockups.html](./phase6-planner-mockups.html). The mockups were the implementation review package; the flow notes below now match the shipped phase-6 planner behavior and keep the anchored screen references for auditability.

## Review Notes

- All displayed prices, sell values, and socket rules come from `data/seed_scenario.json`.
- The planner-owned `Rules` surface is the only place where liquidation permissions and ingredient reserves are configured.
- The mixed-plan and ingredient-liquidation examples are curated late-run workbench states, not the untouched seed landing view. Those state changes are called out explicitly in the screens so the economics stay internally consistent.

## Flow 1: Blessed medicine x3

Primary screen:

- [Desktop 2: Solved Stackable Plan](./phase6-planner-mockups.html#desktop-stackable-plan)

Goal:

- End with `Blessed medicine x3`.

Input line:

- `Stackable` -> `Blessed medicine` -> quantity `3`

Current relevant seed state:

- `Blessed medicine x1` already owned
- `Holy water x0` owned and sold this week at `20g`
- `Runic bone x4` already owned and not sold this week

Planner choice shown in the mock:

- Buy `Holy water x6` for `120g`
- Craft `Blessed medicine` twice

Why the screen matters:

- The planner reads as a craft-vs-buy choice, not a generic recipe viewer.
- The rejected alternative stays legible: two direct buys would cost `200g`, so the craft path saves `80g`.

Resulting state shown:

- Final gold: `219g`
- Final holdings: `Blessed medicine x3`
- Manual-equivalent steps: `3`

## Flow 2: Bronze ring + Sapphire

Primary screens:

- [Desktop 3: Solved Combo Plan](./phase6-planner-mockups.html#desktop-combo-plan)
- [Mobile 2: Planner Detail Sheet](./phase6-planner-mockups.html#mobile-detail)

Goal:

- End with an owned `Bronze ring` socketed with `Sapphire`.

Input line:

- `Combo` -> `Bronze ring` -> `Socket 1 = Sapphire`

Current relevant seed state:

- `Bronze ring` already owned
- `Sapphire piece x9` already owned
- `Bronze ring` socket policy: `max_gems = 1`, `imbue_fee = 50g`

Planner choice shown in the mock:

- Craft `Sapphire` from owned `Sapphire piece x5`
- Assemble `Bronze ring` with the crafted gem

Why the screen matters:

- It shows the planner bridging phase 4 combo mechanics instead of pretending combos are a separate item catalog.
- The only gold movement is the fixed `50g` imbue fee, which keeps the preview easy to audit.

Resulting state shown:

- Final gold: `289g`
- Final holdings: `Bronze ring + Sapphire`
- Projected combo sell value shown in the mock: `70g`

## Flow 3: Mixed Cross-System Goal

Primary screens:

- [Desktop 4: Planner Rules](./phase6-planner-mockups.html#desktop-rules)
- [Desktop 5: Mixed Cross-System Plan](./phase6-planner-mockups.html#desktop-mixed-plan)
- [Desktop 7: Applied Plan Lands In Workbench](./phase6-planner-mockups.html#desktop-applied-plan)

Goal:

- End with `Basic Iron Shield x1`
- End with `Super potion x2`
- End with `Bronze ring + Moonstone`

Input lines:

- `Equipment` -> `Basic Iron Shield` -> quantity `1`
- `Stackable` -> `Super potion` -> quantity `2`
- `Combo` -> `Bronze ring` -> `Socket 1 = Moonstone`

Curated review-state assumptions called out in the mock:

- `Leather Shoes` is explicitly marked `Allow planner to repurpose` in planner rules
- `Silver Talisman` remains protected
- `Bronze ring` is still owned
- `Leather Shoes` is still owned
- `Basic Iron Shield` is not currently owned in this late-run workbench snapshot
- `Moonstone piece x5` is owned

Planner choice shown in the mock:

- Sell `Leather Shoes` for `+25g`
- Buy `Super potion x2` for `-270g`
- Buy `Basic Iron Shield` for `-30g`
- Craft `Moonstone` from owned pieces for `0g`
- Assemble `Bronze ring` with `Moonstone` for `-50g`

Why the screen matters:

- This is the main proof that planner output can span player-owned rules, direct buys, craftable gems, and combo assembly in one preview.
- The mock makes the funding dependency explicit: without the approved `Leather Shoes` liquidation, the plan is short by `11g`.

Resulting state shown:

- Gross spend: `350g`
- Liquidation recovered: `25g`
- Net gold delta: `-325g`
- Final gold: `14g`
- Applied state uses ordinary Action Log rows, not planner-only history

## Flow 4: Ingredient-Funded Purchase

Primary screens:

- [Desktop 4: Planner Rules](./phase6-planner-mockups.html#desktop-rules)
- [Desktop 6: Ingredient Liquidation Plan](./phase6-planner-mockups.html#desktop-liquidation-plan)
- [Mobile 2: Planner Detail Sheet](./phase6-planner-mockups.html#mobile-detail)

Goal:

- End with `Silver Talisman x1`.

Input line:

- `Equipment` -> `Silver Talisman` -> quantity `1`

Curated review-state assumptions called out in the mock:

- Current gold is `82g`
- `Silver Talisman` is not currently owned
- `Aquamarine piece x5`, `Batta berry x7`, `Moonstone piece x5`, and `Runic bone x4` are still owned
- Planner rules include `Batta berry >= 5`, pinned `Moonstone x1`, and pinned `Blessed medicine x1`

Planner choice shown in the mock:

- Sell `Aquamarine piece x4` for `+40g`
- Sell `Batta berry x2` for `+15g`
- Buy `Silver Talisman` for `-130g`

Why the screen matters:

- It shows the hybrid liquidation model the player asked for: sell surplus herbs and gem pieces, but stop before crossing keep floors or reserve lines.
- The chosen steps stay explainable. `Aquamarine piece` is safer to liquidate because it sits four above protection and has lower recipe fan-out than `Batta berry`.
- The mock also makes the non-sells visible: `Moonstone piece x5` stays protected by the pinned `Moonstone x1` reserve, and one `Runic bone` stays protected for pinned `Blessed medicine x1`.

Resulting state shown:

- Gross spend: `130g`
- Liquidation recovered: `55g`
- Net gold delta: `-75g`
- Final gold: `7g`

## Extra Review Reference: Impossible Combo

Primary screen:

- [Desktop 8: Blocked Plan State](./phase6-planner-mockups.html#desktop-blocked-plan)

Goal:

- End with `Bronze necklace + Ruby + Sapphire + Moonstone`

Why it is blocked:

- `Bronze necklace` is neither owned nor sold this week, so the planner has no valid base accessory to acquire before considering gem sourcing.

What to review:

- The failure language names the hard blocker directly.
- The screen stops before secondary noise about gem availability or liquidation policy.

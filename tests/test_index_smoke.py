from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_STORAGE_KEY = "poshy.single-file.lab.v2"
STORAGE_KEY = "poshy.single-file.lab.v3"


def load_seed_scenario() -> dict:
    return json.loads((REPO_ROOT / "data/seed_scenario.json").read_text(encoding="utf-8"))


def format_gold_amount(amount: float) -> str:
    rounded = round(float(amount or 0), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def recipe_by_name(scenario: dict, name: str) -> dict:
    return next(recipe for recipe in scenario["recipes"]["recipes"] if recipe["name"] == name)


def recipe_input_cost(scenario: dict, name: str) -> float:
    recipe = recipe_by_name(scenario, name)
    return sum(
        scenario["ingredient_prices"][ingredient] * count
        for ingredient, count in recipe["ingredients"].items()
    )


def clone_json(value):
    return json.loads(json.dumps(value))


def default_planner_state() -> dict:
    return {
        "repurposable_equipment_ids": {},
        "ingredient_keep_counts": {},
        "pinned_output_reserves": {},
    }


def default_workbench_state(scenario: dict) -> dict:
    return {
        "gold": scenario["inventory"]["gold"],
        "ingredients": clone_json(scenario["inventory"]["ingredients"]),
        "potions": clone_json(scenario["inventory"]["potions"]),
        "gems": clone_json(scenario["inventory"]["gems"]),
        "equipment": clone_json(scenario["inventory"]["equipment"]),
    }


def build_saved_state(
    scenario: dict,
    *,
    workbench: dict | None = None,
    planner: dict | None = None,
    history: list | None = None,
    redo: list | None = None,
) -> dict:
    return {
        "scenario": clone_json(scenario),
        "workbench": clone_json(workbench) if workbench is not None else default_workbench_state(scenario),
        "history": clone_json(history) if history is not None else [],
        "redo": clone_json(redo) if redo is not None else [],
        "planner": clone_json(planner) if planner is not None else default_planner_state(),
    }


def keep_all_ingredients_except(workbench: dict, allowed_names: set[str]) -> dict[str, int]:
    return {
        name: count
        for name, count in workbench["ingredients"].items()
        if count > 0 and name not in allowed_names
    }


def seed_local_storage(context, payload: dict | str, *, key: str = STORAGE_KEY) -> None:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    context.add_init_script(
        f"window.localStorage.setItem({json.dumps(key)}, {json.dumps(raw)});"
    )


def stat_value(page, label: str) -> str:
    stat = page.locator(f'[data-run-stat="{label}"]')
    expect(stat).to_have_count(1)
    return stat.locator("span").inner_text()


def set_data_json(page, payload: dict) -> None:
    page.locator("#data-json").evaluate(
        """(element, value) => {
            element.value = value;
            element.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        json.dumps(payload, indent=2),
    )


def click_workbench_category(page, category: str) -> None:
    page.locator(
        f'button[data-action="set-workbench-category"][data-category="{category}"]'
    ).click()


def inspector_item(page, key: str):
    return page.locator(f'[data-inspector-item="{key}"]:visible')


def accessory_holdings_section(page):
    return page.locator(".holdings-panel .subsection").filter(
        has=page.get_by_role("heading", name="Accessories")
    ).first


def holdings_gear_card(page, equipment_id: str):
    return page.locator(f'[data-holdings-gear-card="{equipment_id}"]').first


def owned_accessory_card(page, equipment_id: str):
    return page.locator(f'[data-owned-accessory-card="{equipment_id}"]').first


def base_equipment_row(page, equipment_id: str):
    return page.locator(f'[data-base-equipment-row="{equipment_id}"]').first


def set_scroll_position(locator, requested_position: int, *, axis: str = "y") -> int:
    scroll_field = "scrollLeft" if axis == "x" else "scrollTop"
    scroll_size = "scrollWidth" if axis == "x" else "scrollHeight"
    client_size = "clientWidth" if axis == "x" else "clientHeight"
    return locator.evaluate(
        f"""(el, nextPosition) => {{
            const maxPosition = Math.max(0, el.{scroll_size} - el.{client_size});
            const clampedPosition = Math.min(maxPosition, nextPosition);
            el.{scroll_field} = clampedPosition;
            return Math.round(el.{scroll_field});
        }}""",
        requested_position,
    )


def assert_scroll_preserved(
    page,
    locator,
    trigger_action,
    *,
    label: str,
    requested_position: int = 240,
    axis: str = "y",
    tolerance: int = 4,
) -> None:
    metrics = locator.evaluate(
        """(el) => ({
            clientWidth: Math.round(el.clientWidth),
            scrollWidth: Math.round(el.scrollWidth),
            clientHeight: Math.round(el.clientHeight),
            scrollHeight: Math.round(el.scrollHeight)
        })"""
    )
    if axis == "x":
        assert metrics["scrollWidth"] > metrics["clientWidth"], (
            f"{label} should overflow horizontally during the smoke test "
            f"(clientWidth={metrics['clientWidth']}, scrollWidth={metrics['scrollWidth']})"
        )
        before = set_scroll_position(locator, requested_position, axis=axis)
        value_getter = "el => Math.round(el.scrollLeft)"
        axis_name = "scrollLeft"
    else:
        assert metrics["scrollHeight"] > metrics["clientHeight"], (
            f"{label} should overflow during the smoke test "
            f"(clientHeight={metrics['clientHeight']}, scrollHeight={metrics['scrollHeight']})"
        )
        before = set_scroll_position(locator, requested_position, axis=axis)
        value_getter = "el => Math.round(el.scrollTop)"
        axis_name = "scrollTop"
    assert before > 0, f"{label} should accept a nonzero {axis_name} position"
    trigger_action()
    page.wait_for_timeout(50)
    after = locator.evaluate(value_getter)
    assert abs(after - before) <= tolerance, (
        f"{label} {axis_name} changed after rerender "
        f"(before={before}, after={after}, tolerance={tolerance})"
    )


def set_window_scroll_y(page, requested_top: int) -> int:
    return page.evaluate(
        """(nextTop) => {
            const maxTop = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
            const clampedTop = Math.min(maxTop, nextTop);
            window.scrollTo(0, clampedTop);
            return Math.round(window.scrollY);
        }""",
        requested_top,
    )


def assert_window_scroll_preserved(
    page,
    trigger_action,
    *,
    label: str,
    requested_top: int = 900,
    tolerance: int = 4,
) -> None:
    max_scroll = page.evaluate(
        "Math.max(0, document.documentElement.scrollHeight - window.innerHeight)"
    )
    assert max_scroll > 0, f"{label} should have enough page height to scroll"
    before = set_window_scroll_y(page, requested_top)
    assert before > 0, f"{label} should accept a nonzero window scroll position"
    trigger_action()
    page.wait_for_timeout(50)
    after = page.evaluate("Math.round(window.scrollY)")
    assert abs(after - before) <= tolerance, (
        f"{label} window.scrollY changed after rerender "
        f"(before={before}, after={after}, tolerance={tolerance})"
    )


def increment_number_input(locator) -> None:
    locator.evaluate(
        """(el) => {
            el.value = String(Number(el.value || 0) + 1);
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }"""
    )


def toggle_checkbox(locator) -> None:
    locator.evaluate(
        """(el) => {
            el.checked = !el.checked;
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }"""
    )


def planner_summary_value(page, label: str) -> str:
    stat = page.locator(".summary-stat").filter(
        has=page.locator("strong", has_text=label)
    )
    expect(stat).to_have_count(1)
    return stat.locator("span").inner_text()


def planner_step_texts(page) -> list[str]:
    return page.locator(".plan-step").evaluate_all(
        """(steps) => steps.map((step) => {
            const index = step.querySelector(".step-index")?.textContent?.trim() || "";
            const title = step.querySelector(".plan-step-copy strong")?.textContent?.trim() || "";
            const detail = step.querySelector(".plan-step-copy .tiny")?.textContent?.trim() || "";
            const delta = step.querySelector(".delta")?.textContent?.trim() || "";
            return [index, title, detail, delta].filter(Boolean).join("\\n");
        })"""
    )


def set_number_input(locator, value: int | float | str) -> None:
    locator.evaluate(
        """(el, nextValue) => {
            el.value = String(nextValue);
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }""",
        str(value),
    )


def planner_scope_button(page, scope: str):
    return page.locator(
        f'button[data-action="set-planner-goal-scope"][data-scope="{scope}"]'
    )


def planner_picker(line, role: str, slot: int | None = None):
    selector = f'.planner-picker[data-picker-role="{role}"]'
    if slot is not None:
        selector += f'[data-picker-slot="{slot}"]'
    return line.locator(selector).first


def open_planner_picker(line, role: str, slot: int | None = None):
    picker = planner_picker(line, role, slot)
    toggle = picker.locator('button[data-action="toggle-planner-picker"]')
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    return picker


def planner_picker_selected_text(line, role: str, slot: int | None = None) -> str:
    return planner_picker(line, role, slot).locator(".planner-picker-copy strong").inner_text().strip()


def planner_picker_search_input(line, role: str, slot: int | None = None):
    return planner_picker(line, role, slot).locator(
        'input[data-action="set-planner-picker-query"]'
    )


def set_planner_picker_search(
    line, role: str, value: str, slot: int | None = None
) -> None:
    picker = open_planner_picker(line, role, slot)
    planner_picker_search_input(line, role, slot).fill(value)
    expect(picker.locator(".planner-picker-list")).to_be_visible()


def planner_picker_option_labels(line, role: str, slot: int | None = None) -> list[str]:
    picker = open_planner_picker(line, role, slot)
    return [text.strip() for text in picker.locator(".planner-picker-option-copy strong").all_inner_texts()]


def select_planner_picker_option(line, role: str, value: str, slot: int | None = None) -> None:
    picker = open_planner_picker(line, role, slot)
    button = picker.locator(
        f'button[data-action="select-planner-picker-option"][data-value="{value}"]'
    )
    if button.count() == 0:
        assert planner_picker_selected_text(line, role, slot).startswith(value)
        return
    button.click()


def planner_delta_texts(page) -> list[str]:
    return page.locator(".planner-delta-row").evaluate_all(
        """(rows) => rows.map((row) => {
            const label = row.querySelector(".planner-delta-copy strong")?.textContent?.trim() || "";
            const detail = row.querySelector(".planner-delta-copy .tiny")?.textContent?.trim() || "";
            const delta = row.querySelector(".delta-pill")?.textContent?.trim() || "";
            return [label, detail, delta].filter(Boolean).join("\\n");
        })"""
    )


def select_option_texts(locator) -> list[str]:
    return [text.strip() for text in locator.locator("option").all_inner_texts()]


def assert_page_has_no_horizontal_overflow(page, *, label: str) -> None:
    metrics = page.evaluate(
        """() => ({
            innerWidth: Math.round(window.innerWidth),
            scrollWidth: Math.round(document.documentElement.scrollWidth)
        })"""
    )
    assert metrics["scrollWidth"] <= metrics["innerWidth"] + 1, (
        f"{label} should not overflow horizontally "
        f"(innerWidth={metrics['innerWidth']}, scrollWidth={metrics['scrollWidth']})"
    )


def assert_locators_fit_width(locator, *, label: str) -> None:
    metrics = locator.evaluate_all(
        """(elements) => elements
            .filter((element) => element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length))
            .map((element, index) => ({
                index,
                clientWidth: Math.round(element.clientWidth),
                scrollWidth: Math.round(element.scrollWidth)
            }))
            .filter((entry) => entry.clientWidth > 0)"""
    )
    for entry in metrics:
        assert entry["scrollWidth"] <= entry["clientWidth"] + 1, (
            f"{label} [{entry['index']}] should not overflow horizontally "
            f"(clientWidth={entry['clientWidth']}, scrollWidth={entry['scrollWidth']})"
        )


def smoke_step(smoke_timing, label: str, *, phase: str, metadata: dict | None = None):
    step_metadata = {"phase": phase}
    if metadata:
        step_metadata.update(metadata)
    return smoke_timing.step(label, metadata=step_metadata)


def smoke_action(
    smoke_timing,
    label: str,
    action,
    *,
    phase: str,
    wait=None,
    metadata: dict | None = None,
):
    step_metadata = {"phase": phase}
    if metadata:
        step_metadata.update(metadata)
    return smoke_timing.run(label, action=action, wait=wait, metadata=step_metadata)


def load_index(page, index_url: str, smoke_timing, *, label: str = "load index", ready=None) -> None:
    smoke_action(
        smoke_timing,
        label,
        lambda: page.goto(index_url, wait_until="domcontentloaded"),
        phase="startup",
        wait=ready,
    )


def reload_page(page, smoke_timing, *, label: str = "reload page", ready=None) -> None:
    smoke_action(
        smoke_timing,
        label,
        lambda: page.reload(wait_until="domcontentloaded"),
        phase="persistence",
        wait=ready,
    )


def open_tab(
    page,
    tab: str,
    smoke_timing,
    *,
    label: str | None = None,
    ready=None,
    metadata: dict | None = None,
) -> None:
    tab_metadata = {"tab": tab}
    if metadata:
        tab_metadata.update(metadata)
    smoke_action(
        smoke_timing,
        label or f"open {tab} tab",
        lambda: page.locator(f'button[data-action="switch-tab"][data-tab="{tab}"]').click(),
        phase="navigation",
        wait=ready,
        metadata=tab_metadata,
    )


def test_index_smoke(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load desktop workbench",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate initial workbench shell", phase="workbench"):
            expect(page).to_have_title("Poshy Lab")
            expect(page.get_by_role("heading", name="Poshy Lab")).to_be_visible()
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
            expect(page.get_by_role("heading", name="Item Details")).to_be_visible()
            expect(page.get_by_role("heading", name="Action Log")).to_be_visible()
            expect(page.locator(".holdings-panel").get_by_role("heading", name="Equipment")).to_be_visible()
            expect(page.locator(".holdings-panel").get_by_role("heading", name="Accessories")).to_be_visible()
            expect(page.locator(".holdings-panel").get_by_role("heading", name="Potions")).to_be_visible()
            expect(page.locator(".holdings-panel").get_by_role("heading", name="Gems")).to_be_visible()
            expect(
                page.locator('button[data-action="set-workbench-category"][data-category="potions"]')
            ).to_be_visible()
            expect(
                page.locator('button[data-action="set-workbench-category"][data-category="accessories"]')
            ).to_be_visible()
            expect(page.locator(".workbench-panel").get_by_role("heading", name="Potions")).to_be_visible()
            expect(page.locator(".holdings-panel")).to_contain_text("Health potion")
            expect(page.locator(".holdings-panel")).to_contain_text("Bronze ring")
            expect(page.locator(".holdings-panel")).to_contain_text("Basic Iron Shield")
            assert stat_value(page, "Equipment") == "4"
            assert stat_value(page, "Gems") == "0"

        with smoke_step(smoke_timing, "inspect workbench categories and holdings detail", phase="workbench"):
            warming_card = page.locator('[data-recipe-card="Warming medicine"]')
            expect(warming_card).to_be_visible()
            expect(warming_card.locator(".potion-meta-line")).to_contain_text("Tier D")
            expect(warming_card.locator(".potion-meta-line")).to_contain_text("Medicine")
            warming_card.get_by_role("button", name="Inspect").click()
            warming_inspector = inspector_item(page, "output:potion:Warming medicine")
            expect(warming_inspector).to_be_visible()
            expect(warming_inspector).to_contain_text("Reactive")
            expect(warming_inspector).to_contain_text("Resets Temp to 0 from a negative number")

            click_workbench_category(page, "gems")
            expect(page.locator(".workbench-panel").get_by_role("heading", name="Gems")).to_be_visible()
            agate_card = page.locator(".workbench-panel .potion-card").filter(
                has=page.locator("h3", has_text="Agate")
            ).first
            expect(agate_card).to_be_visible()
            expect(agate_card.locator(".potion-meta-line")).to_contain_text("Gem")
            expect(agate_card.locator(".potion-meta-line")).to_contain_text("Violet")
            expect(agate_card.locator(".potion-meta-line")).to_contain_text("golem +")
            expect(agate_card.locator(".potion-meta-line")).not_to_contain_text("Tier")
            agate_card.get_by_role("button", name="Inspect").click()
            agate_inspector = inspector_item(page, "output:gem:Agate")
            expect(agate_inspector).to_be_visible()
            expect(agate_inspector).to_contain_text("Violet")
            expect(agate_inspector).to_contain_text("golem +")
            expect(agate_inspector).to_contain_text("gain 2MP every turn you don't cast a spell")
            expect(page.locator(".workbench-side-column .inspector-panel")).to_have_attribute(
                "data-selected-detail-key", "output:gem:Agate"
            )
            expect(page.locator(".workbench-side-column .inspector-panel")).not_to_contain_text(
                "Inspecting"
            )

            click_workbench_category(page, "potions")
            workbench_content = page.locator(".workbench-panel .workbench-content")
            assert_scroll_preserved(
                page,
                workbench_content,
                lambda: page.locator(
                    '[data-recipe-card="Ancient medicine"] button[data-action="inspect-item"]'
                ).dispatch_event("click"),
                label="workbench content",
                requested_position=280,
            )

            holdings_health_row = page.locator(".holdings-panel tr").filter(
                has=page.locator("td", has_text="Health potion")
            ).first
            expect(holdings_health_row.get_by_role("button", name="Inspect")).to_have_count(1)
            holdings_health_row.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "output:potion:Health potion")).to_be_visible()

            herb_holdings = page.locator(".holdings-panel .subsection").filter(
                has=page.get_by_role("heading", name="Herbs")
            ).first
            gem_piece_holdings = page.locator(".holdings-panel .subsection").filter(
                has=page.get_by_role("heading", name="Gem Pieces")
            ).first
            expect(herb_holdings).to_contain_text("Ibsidian shard")
            expect(gem_piece_holdings).not_to_contain_text("Ibsidian shard")
            herb_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Ibsidian shard")
            ).first.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "ingredient:herb:Ibsidian shard")).to_be_visible()

            accessories_holdings = page.locator(".holdings-panel .subsection").filter(
                has=page.get_by_role("heading", name="Accessories")
            ).first
            equipment_holdings = page.locator(".holdings-panel .subsection").filter(
                has=page.get_by_role("heading", name="Equipment")
            ).first
            expect(accessories_holdings).to_contain_text("Silver Talisman")
            expect(accessories_holdings).not_to_contain_text("Basic Iron Shield")
            expect(equipment_holdings).to_contain_text("Basic Iron Shield")
            bronze_ring_holdings = holdings_gear_card(page, "ring-bronze-1")
            expect(bronze_ring_holdings).to_be_visible()
            expect(bronze_ring_holdings).not_to_contain_text("ring-bronze-1")
            bronze_ring_holdings.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "equipment_instance:ring-bronze-1")).to_be_visible()
            expect(inspector_item(page, "equipment_instance:ring-bronze-1")).to_contain_text("0-1 gems @ 50g")
            expect(inspector_item(page, "equipment_instance:ring-bronze-1")).not_to_contain_text("ring-bronze-1")
            expect(inspector_item(page, "equipment_instance:ring-bronze-1")).to_contain_text("+1 STR cap")
            expect(inspector_item(page, "equipment_instance:ring-bronze-1")).not_to_contain_text("Sapphire:")

            shield_holdings = holdings_gear_card(page, "shield-basic-1")
            expect(shield_holdings).to_be_visible()
            shield_holdings.get_by_role("button", name="Inspect").click()
            shield_inspector = inspector_item(page, "equipment_instance:shield-basic-1")
            expect(shield_inspector).to_be_visible()
            expect(shield_inspector).to_contain_text("Equipment")
            expect(shield_inspector).not_to_contain_text("Source Sheet")

            ancient_card = page.locator('[data-recipe-card="Ancient medicine"]')
            expect(ancient_card).to_be_visible()
            expect(ancient_card).to_contain_text("Direct buy is not sold on this level.")
            expect(ancient_card.locator('button[data-action="buy-once"]')).to_be_disabled()

            mana_card = page.locator('[data-recipe-card="Mana potion"]')
            expect(mana_card).to_be_visible()
            expect(mana_card.locator('button[data-action="buy-once"]')).to_be_enabled()
            click_workbench_category(page, "equipment")
            expect(page.locator(".workbench-panel").get_by_role("heading", name="Equipment")).to_be_visible()
            expect(page.locator('button[data-action="buy-equipment"][data-name="Leather Shoes"]')).to_be_visible()
            expect(page.locator('button[data-action="buy-equipment"][data-name="Basic Iron Shield"]')).to_be_visible()
            click_workbench_category(page, "accessories")
            expect(page.locator(".workbench-panel").get_by_role("heading", name="Owned Accessories")).to_be_visible()
            expect(page.locator(".workbench-panel").get_by_role("heading", name="Weekly Listings")).to_be_visible()
            expect(owned_accessory_card(page, "ring-bronze-1")).to_be_visible()
            expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze ring"]')).to_be_visible()
            expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_have_count(0)
            expect(page.locator('button[data-action="buy-equipment"][data-name="Silver Talisman"]')).to_be_visible()
            expect(page.locator('button[data-action="buy-equipment"][data-name="Basic Iron Shield"]')).to_have_count(0)
            page.locator(".workbench-panel tr").filter(
                has=page.locator("td", has_text="Bronze ring")
            ).first.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "equipment_definition:Bronze ring")).to_be_visible()
            expect(inspector_item(page, "equipment_definition:Bronze ring")).to_contain_text("Accessory")
            expect(inspector_item(page, "equipment_definition:Bronze ring")).not_to_contain_text("Source Sheet")
            initial_gold = stat_value(page, "Gold")

        with smoke_step(smoke_timing, "buy ingredients and exercise undo redo reset", phase="workbench"):
            click_workbench_category(page, "herbs")
            lune_row = page.locator(".workbench-panel tr").filter(
                has=page.locator("td", has_text="Lune stone")
            ).first
            expect(lune_row).to_be_visible()
            lune_row.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "ingredient:herb:Lune stone")).to_be_visible()
            lune_row.get_by_role("button", name="Buy").click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Bought Lune stone")
            expect(page.locator(".history-card strong").first).to_contain_text("Bought Lune stone")
            expect(page.locator(".history-card .pill", has_text="Ingredient").first).to_be_visible()
            assert stat_value(page, "Gold") == "329g"

            click_workbench_category(page, "gem_pieces")
            agate_piece_row = page.locator(".workbench-panel tr").filter(
                has=page.locator("td", has_text="Agate piece")
            ).first
            expect(agate_piece_row).to_be_visible()
            agate_piece_row.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "ingredient:gem_piece:Agate piece")).to_be_visible()
            agate_piece_row.get_by_role("button", name="Buy").click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Bought Agate piece")
            assert stat_value(page, "Gold") == "309g"
            assert stat_value(page, "Steps") == "2"

            page.locator('button[data-action="undo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Undid Bought Agate piece")
            assert stat_value(page, "Gold") == "329g"
            page.locator('button[data-action="undo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Undid Bought Lune stone")
            assert stat_value(page, "Gold") == initial_gold
            assert stat_value(page, "Steps") == "0"
            page.locator('button[data-action="redo-action"]').click()
            page.locator('button[data-action="redo-action"]').click()
            assert stat_value(page, "Gold") == "309g"
            assert stat_value(page, "Steps") == "2"

            page.locator('button[data-action="reset-workbench"]').click()
            expect(page.locator(".history-card")).to_have_count(0)
            assert stat_value(page, "Gold") == initial_gold
            assert stat_value(page, "Steps") == "0"

        with smoke_step(smoke_timing, "craft and buy stackables", phase="workbench"):
            click_workbench_category(page, "potions")
            craft_button = page.locator(
                'button[data-action="craft-once"]:not([disabled])'
            ).first
            expect(craft_button).to_be_visible()
            craft_button.click()

            expect(page.locator('[data-role="toast"]')).to_contain_text("Crafted")
            expect(page.locator(".history-card strong").first).to_contain_text("Crafted")
            expect(page.locator('button[data-action="undo-action"]')).to_contain_text("Crafted")
            history_inspect_button = page.locator(".history-card").first.locator('button[data-action="inspect-item"]').first
            expect(history_inspect_button).to_have_count(1)
            selected_history_name = history_inspect_button.get_attribute("data-name")
            selected_history_kind = history_inspect_button.get_attribute("data-kind")
            assert selected_history_name
            assert selected_history_kind
            history_inspect_button.click()
            expect(inspector_item(page, f"output:{selected_history_kind}:{selected_history_name}")).to_be_visible()
            assert stat_value(page, "Steps") == "1"

            page.locator('button[data-action="undo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Undid")
            expect(page.locator(".history-card")).to_have_count(0)
            expect(page.locator('button[data-action="redo-action"]')).to_contain_text("Crafted")
            assert stat_value(page, "Steps") == "0"
            assert stat_value(page, "Gold") == initial_gold

            page.locator('button[data-action="redo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Redid")
            expect(page.locator(".history-card strong").first).to_contain_text("Crafted")
            expect(page.locator('button[data-action="undo-action"]')).to_contain_text("Crafted")
            assert stat_value(page, "Steps") == "1"

            buy_button = page.locator(
                'button[data-action="buy-once"]:not([disabled])'
            ).first
            expect(buy_button).to_be_visible()
            buy_button.click()

            expect(page.locator('[data-role="toast"]')).to_contain_text("Bought")
            expect(page.locator(".history-card strong").first).to_contain_text("Bought")
            assert stat_value(page, "Steps") == "2"

        with smoke_step(smoke_timing, "toggle shop sale visibility and edit base inventory", phase="inventory"):
            open_tab(
                page,
                "shop",
                smoke_timing,
                label="open shop tab",
                ready=lambda: expect(page.get_by_role("heading", name="Direct Buy Potions")).to_be_visible(),
            )
            expect(page.get_by_role("heading", name="Equipment")).to_be_visible()
            expect(page.locator('input[data-action="set-ingredient-sale"][data-name="Lune stone"]')).to_be_checked()
            expect(page.locator('input[data-action="set-output-sale"][data-name="Mana potion"]')).to_be_checked()
            expect(page.locator('input[data-action="set-equipment-sale"][data-name="Bronze ring"]')).to_be_checked()
            expect(page.locator('input[data-action="set-output-sale"][data-name="Ancient medicine"]')).to_have_count(0)
            expect(page.locator('input[data-action="set-equipment-sale"][data-name="Bronze necklace"]')).to_have_count(0)
            page.locator('input[data-action="toggle-zero-shop"]').check()
            expect(page.locator('input[data-action="set-output-sale"][data-name="Ancient medicine"]')).not_to_be_checked()
            bronze_necklace_sale = page.locator(
                'input[data-action="set-equipment-sale"][data-name="Bronze necklace"]'
            )
            expect(bronze_necklace_sale).not_to_be_checked()
            bronze_necklace_sale.check()

            open_tab(
                page,
                "workbench",
                smoke_timing,
                label="return to workbench from shop",
                ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
            )
            click_workbench_category(page, "accessories")
            expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_be_visible()

            open_tab(
                page,
                "inventory",
                smoke_timing,
                label="open inventory tab",
                ready=lambda: expect(page.get_by_role("heading", name="Base Inventory")).to_be_visible(),
            )
            base_gold_input = page.locator("#base-gold")
            updated_gold = str(int(initial_gold.removesuffix("g")) + 7)
            base_gold_input.evaluate(
                """(element, value) => {
                    element.value = value;
                    element.dispatchEvent(new Event("input", { bubbles: true }));
                    element.dispatchEvent(new Event("change", { bubbles: true }));
                }""",
                updated_gold,
            )

            inventory_panel = page.locator('[data-tab-panel="inventory"]')
            expect(inventory_panel.get_by_role("heading", name="Equipment")).to_be_visible()
            expect(inventory_panel.locator('input[data-action="set-base-equipment-name"]')).to_have_count(4)
            boots_hp = inventory_panel.locator(
                'input[data-action="set-base-equipment-hp"][data-id="boots-leather-1"]'
            )
            boots_hp.evaluate(
                """(element, value) => {
                    element.value = value;
                    element.dispatchEvent(new Event("input", { bubbles: true }));
                    element.dispatchEvent(new Event("change", { bubbles: true }));
                }""",
                "5",
            )

            inventory_panel.locator('button[data-action="add-starting-equipment"]').click()
            expect(inventory_panel.locator('input[data-action="set-base-equipment-name"]')).to_have_count(5)
            added_equipment_name = inventory_panel.locator(
                'input[data-action="set-base-equipment-name"][data-id="ape-1"]'
            )
            expect(added_equipment_name).to_have_value("Ape")
            added_equipment_name.evaluate(
                """(element, value) => {
                    element.value = value;
                    element.dispatchEvent(new Event("input", { bubbles: true }));
                    element.dispatchEvent(new Event("change", { bubbles: true }));
                }""",
                "Bronze necklace",
            )
            added_equipment_row = base_equipment_row(inventory_panel, "ape-1")
            expect(
                inventory_panel.locator('input[data-action="set-base-equipment-name"][data-id="ape-1"]')
            ).to_have_value("Bronze necklace")
            expect(added_equipment_row).not_to_contain_text("ape-1")
            expect(added_equipment_row).not_to_contain_text("N/A")
            added_equipment_row.get_by_role("button", name="Remove").click()
            expect(inventory_panel.locator('input[data-action="set-base-equipment-name"]')).to_have_count(4)

        with smoke_step(smoke_timing, "apply base inventory and buy equipment", phase="workbench"):
            page.locator('button[data-action="apply-base-to-workbench"]').dispatch_event("click")
            open_tab(
                page,
                "workbench",
                smoke_timing,
                label="return to workbench after base apply",
                ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
            )
            assert stat_value(page, "Gold") == f"{updated_gold}g"
            leather_shoes_row = holdings_gear_card(page, "boots-leather-1")
            expect(leather_shoes_row).to_contain_text("5/7")
            expect(leather_shoes_row).to_contain_text("17.86g")
            expect(leather_shoes_row).not_to_contain_text("boots-leather-1")
            click_workbench_category(page, "accessories")
            expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_be_visible()

            page.locator('button[data-action="buy-equipment"][data-name="Bronze ring"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Bought Bronze ring")
            expect(page.locator('[data-role="toast"]')).to_contain_text("spend 40g")
            expect(page.locator(".history-card strong").first).to_contain_text("Bought Bronze ring")
            expect(page.locator(".history-card .pill", has_text="Equipment").first).to_be_visible()
            assert stat_value(page, "Equipment") == "5"
            assert stat_value(page, "Gold") == "306g"
            bought_ring_row = holdings_gear_card(page, "bronze-ring-1")
            expect(bought_ring_row).to_contain_text("Bronze ring")
            expect(bought_ring_row).not_to_contain_text("bronze-ring-1")

            page.locator('button[data-action="undo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Undid Bought Bronze ring")
            assert stat_value(page, "Equipment") == "4"
            assert stat_value(page, "Gold") == f"{updated_gold}g"
            expect(page.locator('[data-holdings-gear-card="bronze-ring-1"]')).to_have_count(0)

            page.locator('button[data-action="redo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Redid Bought Bronze ring")
            assert stat_value(page, "Equipment") == "5"
            assert stat_value(page, "Gold") == "306g"
            bought_ring_row = holdings_gear_card(page, "bronze-ring-1")
            expect(bought_ring_row).to_contain_text("Bronze ring")

        reload_page(
            page,
            smoke_timing,
            label="reload after equipment purchase",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "sell equipment and verify persistence", phase="workbench"):
            assert stat_value(page, "Equipment") == "5"
            assert stat_value(page, "Gold") == "306g"
            bought_ring_row = holdings_gear_card(page, "bronze-ring-1")
            expect(bought_ring_row).to_contain_text("Bronze ring")

            bought_ring_row.get_by_role("button", name="Sell").click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Sold Bronze ring")
            expect(page.locator('[data-role="toast"]')).to_contain_text("gain 20g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Bronze ring")
            assert stat_value(page, "Equipment") == "4"
            assert stat_value(page, "Gold") == "326g"
            expect(page.locator('[data-holdings-gear-card="bronze-ring-1"]')).to_have_count(0)

            page.locator('button[data-action="undo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Undid Sold Bronze ring")
            assert stat_value(page, "Equipment") == "5"
            assert stat_value(page, "Gold") == "306g"
            bought_ring_row = holdings_gear_card(page, "bronze-ring-1")
            expect(bought_ring_row).to_contain_text("Bronze ring")

            page.locator('button[data-action="redo-action"]').click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Redid Sold Bronze ring")
            assert stat_value(page, "Equipment") == "4"
            assert stat_value(page, "Gold") == "326g"
            expect(page.locator('[data-holdings-gear-card="bronze-ring-1"]')).to_have_count(0)

            leather_shoes_row = holdings_gear_card(page, "boots-leather-1")
            leather_shoes_row.get_by_role("button", name="Sell").click()
            expect(page.locator('[data-role="toast"]')).to_contain_text("Sold Leather Shoes")
            expect(page.locator('[data-role="toast"]')).to_contain_text("gain 17.86g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Leather Shoes")
            assert stat_value(page, "Equipment") == "3"
            assert stat_value(page, "Gold") == "343.86g"
            expect(page.locator('[data-holdings-gear-card="boots-leather-1"]')).to_have_count(0)

        open_tab(
            page,
            "recipes",
            smoke_timing,
            label="open catalog tab",
            ready=lambda: expect(page.get_by_role("heading", name="Catalog")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate catalog definitions", phase="validation"):
            expect(page.get_by_role("heading", name="Ingredient Definitions")).to_be_visible()
            expect(page.get_by_role("heading", name="Equipment Definitions")).to_be_visible()
            output_definitions_panel = page.locator(".panel").filter(
                has=page.get_by_role("heading", name="Output Definitions")
            ).first
            recipe_names = output_definitions_panel.locator("details.recipe-card summary strong").all_inner_texts()
            assert recipe_names == sorted(recipe_names, key=str.casefold)
            warming_recipe = page.locator("details.recipe-card").filter(
                has=page.locator("summary strong", has_text="Warming medicine")
            ).first
            warming_recipe.locator("summary").click()
            subtype_field = warming_recipe.locator('input[readonly]').first
            tier_field = warming_recipe.locator('select[data-action="set-recipe-tier"]')
            effect_field = warming_recipe.locator('textarea[data-action="set-recipe-effect"]')
            expect(subtype_field).to_have_value("Medicine")
            expect(tier_field).to_have_value("D")
            assert "Resets Temp to 0 from a negative number" in effect_field.input_value()
            agate_recipe = page.locator("details.recipe-card").filter(
                has=page.locator("summary strong", has_text="Agate")
            ).first
            agate_recipe.locator("summary").click()
            expect(agate_recipe).not_to_contain_text("Subtype (derived)")
            expect(agate_recipe.locator('select[data-action="set-recipe-tier"]')).to_have_count(0)
            expect(agate_recipe.locator('input[data-action="set-recipe-price"]')).to_have_count(0)
            expect(agate_recipe).not_to_contain_text("Recipe only")
            expect(agate_recipe.locator('input[data-action="set-gem-color"]')).to_have_value("Violet")
            expect(agate_recipe.locator('input[data-action="set-gem-god"]')).to_have_value("golem +")
            expect(agate_recipe.locator('input[data-action="set-gem-effect"]').first).to_have_value(
                "gain 2MP every turn you don't cast a spell"
            )
            bronze_ring_definition = page.locator("details.recipe-card").filter(
                has=page.locator("summary strong", has_text="Bronze ring")
            ).first
            bronze_ring_definition.locator("summary").click()
            expect(bronze_ring_definition).to_contain_text("0-1 gems @ 50g")
            expect(bronze_ring_definition).not_to_contain_text("Auto-sell in optimizer")

        reload_page(
            page,
            smoke_timing,
            label="reload after catalog validation",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate catalog state after reload", phase="persistence"):
            assert stat_value(page, "Gold") == "343.86g"
            expect(page.locator('[data-holdings-gear-card="boots-leather-1"]')).to_have_count(0)
            page.locator('button[data-action="switch-tab"][data-tab="recipes"]').click()
            bronze_ring_definition = page.locator("details.recipe-card").filter(
                has=page.locator("summary strong", has_text="Bronze ring")
            ).first
            bronze_ring_definition.locator("summary").click()
            expect(bronze_ring_definition).not_to_contain_text("Auto-sell in optimizer")

        with smoke_step(smoke_timing, "exercise mobile workbench navigation and inspector", phase="mobile"):
            mobile_context = browser.new_context(
                viewport={"width": 430, "height": 932},
                is_mobile=True,
                device_scale_factor=2,
            )
            try:
                mobile = mobile_context.new_page()
                mobile.goto(index_url, wait_until="domcontentloaded")

                hero_toggle = mobile.locator("#hero-mobile-toggle")
                expect(hero_toggle).to_be_visible()
                expect(hero_toggle).to_have_text("Show Intro")
                expect(mobile.locator(".status-stack")).not_to_be_visible()

                mobile_holdings_button = mobile.locator(
                    'button[data-action="set-workbench-mobile-section"][data-section="holdings"]'
                )
                mobile_workbench_button = mobile.locator(
                    'button[data-action="set-workbench-mobile-section"][data-section="workbench"]'
                )
                mobile_log_button = mobile.locator(
                    'button[data-action="set-workbench-mobile-section"][data-section="log"]'
                )
                expect(mobile_holdings_button).to_be_visible()
                expect(mobile_log_button).to_be_visible()
                expect(
                    mobile.locator('button[data-action="set-workbench-mobile-section"][data-section="details"]')
                ).to_have_count(0)
                expect(mobile.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
                expect(mobile.get_by_role("heading", name="Current Holdings")).not_to_be_visible()
                expect(mobile.get_by_role("heading", name="Action Log")).not_to_be_visible()
                expect(mobile.locator('[data-role="mobile-inspector"]:visible')).to_have_count(0)

                mobile_holdings_button.click()
                expect(mobile.get_by_role("heading", name="Current Holdings")).to_be_visible()
                expect(mobile.get_by_role("heading", name="Alchemy Workbench")).not_to_be_visible()

                mobile_log_button.click()
                expect(mobile.get_by_role("heading", name="Action Log")).to_be_visible()
                expect(mobile.get_by_role("heading", name="Current Holdings")).not_to_be_visible()

                mobile_workbench_button.click()
                mobile_holdings_button.click()
                holdings_gear_card(mobile, "boots-leather-1").get_by_role("button", name="Inspect").click()
                mobile_sheet = mobile.locator('[data-role="mobile-inspector"]:visible')
                expect(mobile_sheet).to_be_visible()
                expect(mobile.get_by_role("heading", name="Current Holdings")).to_be_visible()
                expect(mobile_sheet).to_contain_text("Leather Shoes")
                expect(
                    mobile_sheet.locator('[data-inspector-item="equipment_instance:boots-leather-1"]')
                ).to_contain_text("7/7")
                expect(mobile_sheet).not_to_contain_text("boots-leather-1")
                mobile_sheet.get_by_role("button", name="Close", exact=True).click()
                expect(mobile.locator('[data-role="mobile-inspector"]:visible')).to_have_count(0)

                hero_toggle.click()
                expect(hero_toggle).to_have_text("Hide Intro")
                expect(mobile.locator(".status-stack")).to_be_visible()
            finally:
                mobile_context.close()

        context.close()
        browser.close()


def test_index_planner_tab_and_mobile_sections(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        load_index(
            page,
            index_url,
            smoke_timing,
            label="load desktop planner shell",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate planner desktop layout", phase="planner"):
            assert page.locator("#tab-buttons .tab-button").all_inner_texts() == [
                "Workbench",
                "Planner",
                "Inventory",
                "For Sale",
                "Catalog",
                "Data Studio",
            ]

            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            expect(page.get_by_role("heading", name="Goal Builder")).to_be_visible()
            expect(page.get_by_role("heading", name="Current Holdings")).to_be_visible()
            expect(page.get_by_role("heading", name="Plan Preview")).to_be_visible()
            expect(page.get_by_role("heading", name="Item Details")).to_be_visible()
            expect(page.get_by_role("heading", name="Equipment Repurpose Rules")).to_be_visible()
            expect(page.locator('[data-planner-status="draft"]')).to_contain_text("No plan yet")
            expect(planner_scope_button(page, "actionable")).to_be_visible()
            expect(planner_scope_button(page, "all")).to_be_visible()
            expect(planner_scope_button(page, "actionable")).to_have_attribute(
                "aria-pressed", "true"
            )

        mobile_context = browser.new_context(
            viewport={"width": 430, "height": 932},
            is_mobile=True,
            device_scale_factor=2,
        )
        mobile = mobile_context.new_page()
        load_index(
            mobile,
            index_url,
            smoke_timing,
            label="load mobile planner shell",
            ready=lambda: expect(mobile.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "exercise mobile planner sections and preview sheet", phase="mobile"):
            mobile.locator('button[data-action="switch-tab"][data-tab="planner"]').click()

            goals_button = mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="goals"]'
            )
            holdings_button = mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="holdings"]'
            )
            plan_button = mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="plan"]'
            )
            rules_button = mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="rules"]'
            )
            expect(goals_button).to_be_visible()
            expect(holdings_button).to_be_visible()
            expect(plan_button).to_be_visible()
            expect(rules_button).to_be_visible()
            expect(planner_scope_button(mobile, "actionable")).to_be_visible()
            expect(planner_scope_button(mobile, "all")).to_be_visible()

            holdings_button.click()
            mobile.locator('[data-planner-holdings-gear-card="ring-bronze-1"]').get_by_role(
                "button", name="Inspect"
            ).click()
            planner_mobile_sheet = mobile.locator('[data-role="mobile-inspector"]:visible')
            expect(planner_mobile_sheet).to_be_visible()
            expect(planner_mobile_sheet).to_contain_text("Bronze ring")
            planner_mobile_sheet.get_by_role("button", name="Close", exact=True).click()
            expect(mobile.locator('[data-role="mobile-inspector"]:visible')).to_have_count(0)

            goals_button.click()
            mobile.get_by_role("button", name="Add Stackable Line").click()
            line = mobile.locator("[data-planner-line]").first
            expect(planner_picker(line, "stackable").locator(".planner-picker-list")).to_be_visible()
            expect(planner_picker_search_input(line, "stackable")).to_be_visible()
            assert planner_picker_selected_text(line, "stackable") == "No output selected"
            select_planner_picker_option(line, "stackable", "Blessed medicine")
            set_number_input(line.locator('input[data-action="set-planner-line-quantity"]'), 3)

            plan_button.click()
            mobile.get_by_role("button", name="Preview Plan").click()
            expect(mobile.locator(".plan-step")).to_have_count(3)
            mobile.locator('button[data-action="select-planner-step"]').first.click()
            step_sheet = mobile.locator('[data-role="planner-mobile-sheet"]')
            expect(step_sheet).to_be_visible()
            expect(step_sheet).to_contain_text("Buy Holy water x6")
            step_sheet.get_by_role("button", name="View Rules").click()
            expect(mobile.locator('[data-role="planner-mobile-sheet"]')).to_have_count(0)
            expect(mobile.get_by_role("heading", name="Ingredient Reserves")).to_be_visible()

        mobile_context.close()
        context.close()
        browser.close()


def test_index_planner_goal_builder_scope_filters_and_preserves_selection(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner scope filter page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate planner scope filters preserve selection", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()

            page.get_by_role("button", name="Add Equipment Line").click()
            equipment_line = page.locator("[data-planner-line]").first
            actionable_equipment_options = planner_picker_option_labels(
                equipment_line, "equipment"
            )
            assert "Basic Iron Shield" in actionable_equipment_options
            assert "Bronze necklace" not in actionable_equipment_options

            page.get_by_role("button", name="Add Combo Line").click()
            combo_line = page.locator("[data-planner-line]").nth(1)
            actionable_combo_options = planner_picker_option_labels(
                combo_line, "combo-base"
            )
            assert "Bronze ring" in actionable_combo_options
            assert "Bronze necklace" not in actionable_combo_options

            planner_scope_button(page, "all").click()
            assert "Bronze necklace" in planner_picker_option_labels(equipment_line, "equipment")
            assert "Bronze necklace" in planner_picker_option_labels(combo_line, "combo-base")

            select_planner_picker_option(equipment_line, "equipment", "Bronze necklace")
            planner_scope_button(page, "actionable").click()

            assert planner_picker_selected_text(equipment_line, "equipment").startswith(
                "Bronze necklace"
            )
            preserved_options = planner_picker_option_labels(equipment_line, "equipment")
            assert preserved_options[0] == "Bronze necklace (outside current filter)"
            assert "Bronze necklace" not in planner_picker_option_labels(combo_line, "combo-base")

        context.close()
        browser.close()


def test_index_planner_actionable_filter_ignores_current_gold(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    workbench = default_workbench_state(scenario)
    workbench["gold"] = 0
    saved_state = build_saved_state(scenario, workbench=workbench)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner with zero gold state",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate actionable filter ignores current gold", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()

            page.get_by_role("button", name="Add Stackable Line").click()
            stackable_line = page.locator("[data-planner-line]").first
            stackable_options = planner_picker_option_labels(stackable_line, "stackable")
            assert "Blessed medicine" in stackable_options

            page.get_by_role("button", name="Add Combo Line").click()
            combo_line = page.locator("[data-planner-line]").nth(1)
            select_planner_picker_option(combo_line, "combo-base", "Bronze ring")
            gem_options = planner_picker_option_labels(combo_line, "combo-gem", slot=0)
            assert "Sapphire" in gem_options

        context.close()
        browser.close()


def test_index_planner_new_lines_open_empty_and_search_first(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner new-line picker page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "exercise stackable picker default state and search", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Stackable Line").click()
            stackable_line = page.locator("[data-planner-line]").first
            expect(planner_picker_search_input(stackable_line, "stackable")).to_be_visible()
            assert planner_picker_selected_text(stackable_line, "stackable") == "No output selected"
            set_planner_picker_search(stackable_line, "stackable", "blessed")
            assert planner_picker_option_labels(stackable_line, "stackable") == [
                "Blessed medicine"
            ]
            select_planner_picker_option(stackable_line, "stackable", "Blessed medicine")
            expect(planner_picker_search_input(stackable_line, "stackable")).to_have_count(0)
            assert planner_picker_selected_text(stackable_line, "stackable") == "Blessed medicine"

        with smoke_step(smoke_timing, "exercise combo picker default state and search", phase="planner"):
            page.get_by_role("button", name="Add Combo Line").click()
            combo_line = page.locator("[data-planner-line]").nth(1)
            expect(planner_picker_search_input(combo_line, "combo-base")).to_be_visible()
            expect(
                combo_line.locator('.planner-picker[data-picker-role="combo-gem"][data-picker-slot="0"]')
            ).to_have_count(0)
            set_planner_picker_search(combo_line, "combo-base", "bronze ring")
            select_planner_picker_option(combo_line, "combo-base", "Bronze ring")
            expect(planner_picker(combo_line, "combo-gem", slot=0)).to_be_visible()
            expect(planner_picker_search_input(combo_line, "combo-gem", slot=0)).to_be_visible()

        context.close()
        browser.close()


def test_index_planner_actionable_equipment_scope_includes_repurposable_socketed_bases(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    workbench = default_workbench_state(scenario)
    workbench["equipment"].append(
        {
            "id": "bronze-necklace-1",
            "base_name": "Bronze necklace",
            "current_hp": None,
            "socketed_gems": ["Ruby"],
        }
    )
    saved_state = build_saved_state(scenario, workbench=workbench)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner with repurposable combo base",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "toggle repurpose rule to expand equipment scope", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Equipment Line").click()

            equipment_line = page.locator("[data-planner-line]").first
            assert "Bronze necklace" not in planner_picker_option_labels(
                equipment_line, "equipment"
            )

            page.locator(
                'input[data-action="toggle-planner-repurpose"][data-id="bronze-necklace-1"]'
            ).check()

            assert "Bronze necklace" in planner_picker_option_labels(
                equipment_line, "equipment"
            )

        context.close()
        browser.close()


def test_index_planner_goal_scope_toggle_does_not_invalidate_preview(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner scope toggle preview page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "build planner preview before scope toggle", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Stackable Line").click()
            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "stackable", "Blessed medicine")
            set_number_input(line.locator('input[data-action="set-planner-line-quantity"]'), 3)
            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Steps") == "3"

        with smoke_step(smoke_timing, "toggle planner scope without invalidating preview", phase="planner"):
            planner_scope_button(page, "all").click()
            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Steps") == "3"

            planner_scope_button(page, "actionable").click()
            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Steps") == "3"

        context.close()
        browser.close()


def test_index_planner_wrap_overflow_and_scroll_guards(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        desktop_context = browser.new_context(viewport={"width": 1440, "height": 900})
        desktop = desktop_context.new_page()
        load_index(
            desktop,
            index_url,
            smoke_timing,
            label="load desktop planner overflow page",
            ready=lambda: expect(desktop.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "configure desktop planner preview", phase="planner"):
            desktop.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            desktop.get_by_role("button", name="Add Stackable Line").click()
            desktop_line = desktop.locator("[data-planner-line]").first
            select_planner_picker_option(desktop_line, "stackable", "Blessed medicine")
            set_number_input(
                desktop_line.locator('input[data-action="set-planner-line-quantity"]'),
                3,
            )
            desktop.get_by_role("button", name="Preview Plan").click()

        with smoke_step(smoke_timing, "validate desktop planner overflow and scroll guards", phase="planner"):
            assert_page_has_no_horizontal_overflow(desktop, label="desktop planner page")
            assert_locators_fit_width(
                desktop.locator(
                    ".planner-holdings-panel, .goal-line, .planner-picker, .planner-delta-row, .plan-step, .planner-rules-panel, .planner-rule-card"
                ),
                label="desktop planner panels",
            )
            assert_scroll_preserved(
                desktop,
                desktop.locator(".planner-holdings-panel .holdings-scroll"),
                lambda: desktop.locator(
                    '[data-planner-holdings-gear-card="ring-bronze-1"] button[data-action="inspect-item"]'
                ).dispatch_event("click"),
                label="planner holdings scroll",
                requested_position=420,
            )
            assert_scroll_preserved(
                desktop,
                desktop.locator(".planner-rule-list").first,
                lambda: set_number_input(
                    desktop.locator(
                        'input[data-action="set-planner-keep-count"][data-name="Batta berry"]'
                    ),
                    3,
                ),
                label="planner reserve scroll",
                requested_position=320,
            )
            assert_scroll_preserved(
                desktop,
                desktop.locator(".planner-rule-list").first,
                lambda: set_number_input(
                    desktop.locator(
                        'input[data-action="set-planner-keep-count"][data-name="Batta berry"]'
                    ),
                    4,
                ),
                label="planner reserve scroll at bottom",
                requested_position=9999,
            )

        mobile_context = browser.new_context(
            viewport={"width": 430, "height": 932},
            is_mobile=True,
            device_scale_factor=2,
        )
        mobile = mobile_context.new_page()
        load_index(
            mobile,
            index_url,
            smoke_timing,
            label="load mobile planner overflow page",
            ready=lambda: expect(mobile.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "validate mobile planner overflow and section guards", phase="mobile"):
            mobile.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            mobile.get_by_role("button", name="Add Stackable Line").click()
            mobile_line = mobile.locator("[data-planner-line]").first
            select_planner_picker_option(mobile_line, "stackable", "Blessed medicine")
            set_number_input(
                mobile_line.locator('input[data-action="set-planner-line-quantity"]'),
                3,
            )
            mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="holdings"]'
            ).click()
            assert_page_has_no_horizontal_overflow(mobile, label="mobile planner holdings page")
            assert_locators_fit_width(
                mobile.locator(".planner-holdings-panel, [data-planner-holdings-gear-card]"),
                label="mobile planner holdings",
            )
            assert_window_scroll_preserved(
                mobile,
                lambda: mobile.locator(
                    '[data-planner-holdings-gear-card="ring-bronze-1"] button[data-action="inspect-item"]'
                ).dispatch_event("click"),
                label="mobile planner holdings page",
                requested_top=320,
            )
            mobile.locator('[data-role="mobile-inspector"]:visible').get_by_role(
                "button", name="Close", exact=True
            ).click()

            mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="plan"]'
            ).click()
            mobile.get_by_role("button", name="Preview Plan").click()
            assert_page_has_no_horizontal_overflow(mobile, label="mobile planner plan page")
            assert_locators_fit_width(
                mobile.locator(".planner-delta-row, .plan-step"),
                label="mobile planner plan rows",
            )

            mobile.locator(
                'button[data-action="set-planner-mobile-section"][data-section="rules"]'
            ).click()
            assert_page_has_no_horizontal_overflow(mobile, label="mobile planner rules page")
            assert_locators_fit_width(
                mobile.locator(".planner-rules-panel, .planner-rule-card"),
                label="mobile planner rule cards",
            )

        mobile_context.close()
        desktop_context.close()
        browser.close()


def test_index_planner_inspector_stays_visible_and_resets_scroll(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    modified_scenario = json.loads(json.dumps(scenario))
    modified_scenario["equipment"]["definitions"]["Bronze ring"]["effects"].extend(
        [f"Planner inspector filler effect {index}" for index in range(1, 19)]
    )
    saved_state = build_saved_state(modified_scenario)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        seed_local_storage(context, saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner inspector scroll page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "inspect planner holdings item and seed scroll state", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()

            page.locator('[data-planner-holdings-gear-card="ring-bronze-1"]').get_by_role(
                "button", name="Inspect"
            ).click()
            inspector_scroll = page.locator(".planner-inspector-panel .inspector-scroll")
            expect(inspector_scroll).to_be_visible()
            assert set_scroll_position(inspector_scroll, 9999) > 0

        with smoke_step(smoke_timing, "verify planner inspector stays visible and resets scroll", phase="planner"):
            assert set_window_scroll_y(page, 900) > 0
            page.locator('[data-planner-rule="talisman-silver-1"]').get_by_role(
                "button", name="Inspect"
            ).click()

            expect(page.locator(".planner-inspector-panel")).to_be_visible()
            panel_top = page.locator(".planner-inspector-panel").evaluate(
                "el => Math.round(el.getBoundingClientRect().top)"
            )
            assert 0 <= panel_top <= 180
            reset_scroll = page.locator(".planner-inspector-panel .inspector-scroll").evaluate(
                "el => Math.round(el.scrollTop)"
            )
            assert reset_scroll <= 4

        context.close()
        browser.close()


def test_index_preserves_scroll_positions(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    modified_scenario = json.loads(json.dumps(scenario))
    modified_scenario["equipment"]["definitions"]["Bronze ring"]["effects"].extend(
        [f"Scroll filler effect {index}" for index in range(1, 19)]
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 810})
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load scroll preservation page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "import modified scenario for scroll checks", phase="validation"):
            page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()
            set_data_json(page, modified_scenario)
            page.locator('button[data-action="import-scenario-json"]').click()

            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()

        with smoke_step(smoke_timing, "preserve workbench holdings and inspector scroll", phase="workbench"):
            click_workbench_category(page, "potions")
            assert_scroll_preserved(
                page,
                page.locator(".workbench-panel .workbench-content"),
                lambda: page.locator(
                    '[data-recipe-card="Ancient medicine"] button[data-action="inspect-item"]'
                ).dispatch_event("click"),
                label="workbench content",
                requested_position=280,
            )

            assert_scroll_preserved(
                page,
                page.locator(".holdings-panel .holdings-scroll"),
                lambda: page.locator(
                    'button[data-action="sell-stackable"][data-bucket="ingredients"][data-name="Alexandrite piece"]'
                ).dispatch_event("click"),
                label="holdings scroll",
                requested_position=420,
            )

            click_workbench_category(page, "accessories")
            ring_card = owned_accessory_card(page, "ring-bronze-1")
            expect(ring_card).to_be_visible()
            ring_card.get_by_role("button", name="Inspect").click()
            expect(inspector_item(page, "equipment_instance:ring-bronze-1")).to_be_visible()
            assert_scroll_preserved(
                page,
                page.locator(".workbench-side-column .inspector-panel .inspector-scroll"),
                lambda: page.locator(
                    'button[data-action="sell-stackable"][data-bucket="ingredients"][data-name="Lune stone"]'
                ).dispatch_event("click"),
                label="inspector panel",
                requested_position=280,
            )

        with smoke_step(smoke_timing, "preserve action log inventory and shop scroll", phase="navigation"):
            click_workbench_category(page, "herbs")
            for _ in range(12):
                page.locator(
                    'button[data-action="buy-ingredient"][data-name="Lune stone"]'
                ).dispatch_event("click")
            assert page.locator(".history-card").count() >= 12
            assert_scroll_preserved(
                page,
                page.locator(".action-log-panel .grid-list"),
                lambda: page.locator(".workbench-panel tr").filter(
                    has=page.locator("td", has_text="Lune stone")
                ).first.get_by_role("button", name="Inspect").dispatch_event("click"),
                label="action log",
                requested_position=360,
            )

            page.locator('button[data-action="switch-tab"][data-tab="inventory"]').click()
            expect(page.get_by_role("heading", name="Base Inventory")).to_be_visible()
            assert_window_scroll_preserved(
                page,
                lambda: increment_number_input(
                    page.locator('input[data-action="set-base-ingredient"][data-name="Lune stone"]')
                ),
                label="inventory page",
            )

            page.locator('button[data-action="switch-tab"][data-tab="shop"]').click()
            expect(page.get_by_role("heading", name="For Sale This Week")).to_be_visible()
            page.locator('input[data-action="toggle-zero-shop"]').check()
            assert_window_scroll_preserved(
                page,
                lambda: toggle_checkbox(
                    page.locator('input[data-action="set-equipment-sale"][data-name="Bronze ring"]')
                ),
                label="shop page",
            )

        with smoke_step(smoke_timing, "preserve mobile inspector scroll", phase="mobile"):
            page.set_viewport_size({"width": 430, "height": 932})
            page.wait_for_timeout(50)
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            holdings_button = page.locator(
                'button[data-action="set-workbench-mobile-section"][data-section="holdings"]'
            )
            expect(holdings_button).to_be_visible()
            holdings_button.click()
            holdings_gear_card(page, "ring-bronze-1").get_by_role("button", name="Inspect").click()
            mobile_sheet = page.locator(".mobile-inspector-sheet:visible")
            expect(mobile_sheet).to_be_visible()
            assert_scroll_preserved(
                page,
                mobile_sheet,
                lambda: page.locator("#hero-mobile-toggle").dispatch_event("click"),
                label="mobile inspector sheet",
                requested_position=320,
            )

        context.close()
        browser.close()


def test_index_accessory_combo_assembly(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    sapphire_sell = scenario["ingredient_prices"]["Sapphire piece"] * 5 * scenario["market"]["sell_markdown"]
    ring_base_sell = (
        scenario["equipment"]["definitions"]["Bronze ring"]["buy_price"] * scenario["market"]["sell_markdown"]
    )
    expected_ring_combo_sell = ring_base_sell + sapphire_sell

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        toast = page.locator('[data-role="toast"]')

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load accessory combo assembly page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "enable accessory market sale and buy base necklace", phase="workbench"):
            page.locator('button[data-action="switch-tab"][data-tab="shop"]').click()
            page.locator('input[data-action="toggle-zero-shop"]').check()
            bronze_necklace_sale = page.locator(
                'input[data-action="set-equipment-sale"][data-name="Bronze necklace"]'
            )
            expect(bronze_necklace_sale).not_to_be_checked()
            bronze_necklace_sale.check()

            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            click_workbench_category(page, "accessories")
            page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]').click()
            expect(toast).to_contain_text("Bought Bronze necklace")
            assert stat_value(page, "Gold") == "189g"
            assert stat_value(page, "Equipment") == "5"

        with smoke_step(smoke_timing, "craft gems and assemble bronze ring combo", phase="workbench"):
            click_workbench_category(page, "gems")
            for gem_name in ["Sapphire", "Ruby", "Garnet"]:
                gem_card = page.locator(f'[data-recipe-card="{gem_name}"]')
                expect(gem_card).to_be_visible()
                gem_card.locator('button[data-action="craft-once"]').click()
                expect(toast).to_contain_text(f"Crafted {gem_name}")
            assert stat_value(page, "Gems") == "3"

            click_workbench_category(page, "accessories")
            accessories = accessory_holdings_section(page)
            ring_card = owned_accessory_card(page, "ring-bronze-1")
            expect(ring_card).to_be_visible()
            expect(ring_card).not_to_contain_text("ring-bronze-1")
            ring_card.get_by_role("button", name="Inspect").click()
            ring_inspector = inspector_item(page, "equipment_instance:ring-bronze-1")
            expect(ring_inspector).to_be_visible()
            expect(ring_inspector).to_contain_text("Current Sockets")
            expect(ring_inspector).not_to_contain_text("Available Owned Gems")
            expect(ring_inspector.locator(
                'button[data-action="assemble-accessory"][data-id="ring-bronze-1"]'
            )).to_have_count(0)
            assemble_ring_button = ring_card.locator(
                'button[data-action="assemble-accessory"][data-id="ring-bronze-1"]'
            )
            expect(assemble_ring_button).to_be_disabled()
            expect(ring_inspector).to_contain_text("+1 STR cap")
            expect(ring_inspector).to_contain_text("-1 SKI cap")
            expect(ring_inspector).not_to_contain_text("Sapphire: Increases FAB by 1")
            ring_card.locator(
                'select[data-action="set-accessory-combo-slot"][data-id="ring-bronze-1"][data-slot="0"]'
            ).select_option("Sapphire")
            expect(assemble_ring_button).to_be_enabled()
            assemble_ring_button.click()
            expect(toast).to_contain_text("Assembled Bronze ring")
            expect(toast).to_contain_text("socket Sapphire x1")
            expect(toast).to_contain_text("spend 50g")
            assert stat_value(page, "Gold") == "139g"
            assert stat_value(page, "Gems") == "2"
            ring_holdings = holdings_gear_card(page, "ring-bronze-1")
            expect(ring_holdings).to_contain_text("Sockets: Sapphire")
            expect(ring_holdings).to_contain_text("70g")
            expect(ring_inspector).to_contain_text("Sell Breakdown")
            expect(ring_inspector).to_contain_text("+1 STR cap")
            expect(ring_inspector).to_contain_text("-1 SKI cap")
            expect(ring_inspector).to_contain_text("Sapphire: Increases FAB by 1")
            expect(ring_inspector).to_contain_text("Sapphire: Increases vision by 2")
            expect(ring_inspector).to_contain_text("Sapphire")
            expect(ring_inspector).to_contain_text("Total")
            expect(ring_inspector).to_contain_text("70g")

            page.locator('button[data-action="undo-action"]').click()
            expect(toast).to_contain_text("Undid Assembled Bronze ring")
            assert stat_value(page, "Gold") == "189g"
            assert stat_value(page, "Gems") == "3"
            ring_holdings = holdings_gear_card(page, "ring-bronze-1")
            expect(ring_holdings).not_to_contain_text("Sockets: Sapphire")
            expect(ring_holdings).to_contain_text("20g")

            page.locator('button[data-action="redo-action"]').click()
            expect(toast).to_contain_text("Redid Assembled Bronze ring")
            assert stat_value(page, "Gold") == "139g"
            assert stat_value(page, "Gems") == "2"
            ring_holdings = holdings_gear_card(page, "ring-bronze-1")
            expect(ring_holdings).to_contain_text("Sockets: Sapphire")
            expect(ring_holdings).to_contain_text("70g")

        with smoke_step(smoke_timing, "assemble and disassemble bronze necklace combo", phase="workbench"):
            necklace_card = owned_accessory_card(page, "bronze-necklace-1")
            expect(necklace_card).to_be_visible()
            necklace_card.get_by_role("button", name="Inspect").click()
            necklace_inspector = inspector_item(page, "equipment_instance:bronze-necklace-1")
            expect(necklace_inspector).to_be_visible()
            expect(necklace_inspector.locator(
                'button[data-action="disassemble-accessory"][data-id="bronze-necklace-1"]'
            )).to_have_count(0)
            necklace_card.locator(
                'select[data-action="set-accessory-combo-slot"][data-id="bronze-necklace-1"][data-slot="0"]'
            ).select_option("Ruby")
            necklace_card.locator(
                'select[data-action="set-accessory-combo-slot"][data-id="bronze-necklace-1"][data-slot="1"]'
            ).select_option("Garnet")
            necklace_card.locator(
                'button[data-action="assemble-accessory"][data-id="bronze-necklace-1"]'
            ).click()
            expect(toast).to_contain_text("Assembled Bronze necklace")
            expect(toast).to_contain_text("spend 50g")
            assert stat_value(page, "Gold") == "89g"
            assert stat_value(page, "Gems") == "0"
            necklace_holdings = holdings_gear_card(page, "bronze-necklace-1")
            expect(necklace_holdings).to_contain_text("Sockets: Ruby, Garnet")
            expect(necklace_holdings).to_contain_text("175g")

            necklace_card = owned_accessory_card(page, "bronze-necklace-1")
            necklace_card.locator(
                'button[data-action="disassemble-accessory"][data-id="bronze-necklace-1"]'
            ).click()
            expect(toast).to_contain_text("Disassembled Bronze necklace")
            assert stat_value(page, "Gold") == "89g"
            assert stat_value(page, "Gems") == "2"
            necklace_holdings = holdings_gear_card(page, "bronze-necklace-1")
            expect(necklace_holdings).not_to_contain_text("Sockets: Ruby, Garnet")
            expect(necklace_holdings).to_contain_text("75g")
            expect(
                owned_accessory_card(page, "bronze-necklace-1").locator(
                    'select[data-action="set-accessory-combo-slot"][data-id="bronze-necklace-1"][data-slot="0"]'
                )
            ).to_have_value("Ruby")
            expect(
                owned_accessory_card(page, "bronze-necklace-1").locator(
                    'select[data-action="set-accessory-combo-slot"][data-id="bronze-necklace-1"][data-slot="1"]'
                )
            ).to_have_value("Garnet")

            page.locator('button[data-action="undo-action"]').click()
            expect(toast).to_contain_text("Undid Disassembled Bronze necklace")
            assert stat_value(page, "Gems") == "0"
            necklace_holdings = holdings_gear_card(page, "bronze-necklace-1")
            expect(necklace_holdings).to_contain_text("Sockets: Ruby, Garnet")
            expect(necklace_holdings).to_contain_text("175g")

            page.locator('button[data-action="redo-action"]').click()
            expect(toast).to_contain_text("Redid Disassembled Bronze necklace")
            assert stat_value(page, "Gems") == "2"
            necklace_holdings = holdings_gear_card(page, "bronze-necklace-1")
            expect(necklace_holdings).not_to_contain_text("Sockets: Ruby, Garnet")
            expect(necklace_holdings).to_contain_text("75g")

        with smoke_step(smoke_timing, "sell assembled bronze ring combo", phase="workbench"):
            gold_before_sell = float(stat_value(page, "Gold").removesuffix("g"))
            ring_holdings = holdings_gear_card(page, "ring-bronze-1")
            expect(ring_holdings).to_contain_text(f"{int(expected_ring_combo_sell)}g")
            ring_holdings.get_by_role("button", name="Sell").click()
            expect(toast).to_contain_text("Sold Bronze ring")
            expect(toast).to_contain_text(f"gain {int(expected_ring_combo_sell)}g")
            assert float(stat_value(page, "Gold").removesuffix("g")) == gold_before_sell + expected_ring_combo_sell
            assert stat_value(page, "Equipment") == "4"
            expect(page.locator('[data-holdings-gear-card="ring-bronze-1"]')).to_have_count(0)

        context.close()
        browser.close()


def test_index_stackable_sell_flows(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    modified_scenario = json.loads(json.dumps(scenario))
    recipe_by_name(modified_scenario, "Health potion")["price"] = None
    modified_scenario["inventory"]["gems"]["Agate"] = 1

    markdown = modified_scenario["market"]["sell_markdown"]
    blessed_sell = recipe_by_name(scenario, "Blessed medicine")["price"] * markdown
    health_sell = recipe_input_cost(modified_scenario, "Health potion") * markdown
    lune_sell = modified_scenario["ingredient_prices"]["Lune stone"] * markdown
    alexandrite_sell = modified_scenario["ingredient_prices"]["Alexandrite piece"] * markdown
    agate_sell = recipe_input_cost(modified_scenario, "Agate") * markdown
    total_sell_gain = blessed_sell + health_sell + lune_sell + alexandrite_sell + agate_sell

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        toast = page.locator('[data-role="toast"]')

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load stackable sell flow page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "import modified scenario for sell flow coverage", phase="validation"):
            page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()
            set_data_json(page, modified_scenario)
            page.locator('button[data-action="import-scenario-json"]').click()

            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
            assert stat_value(page, "Gold") == "339g"
            assert stat_value(page, "Gems") == "1"

        herb_holdings = page.locator(".holdings-panel .subsection").filter(
            has=page.get_by_role("heading", name="Herbs")
        ).first
        gem_piece_holdings = page.locator(".holdings-panel .subsection").filter(
            has=page.get_by_role("heading", name="Gem Pieces")
        ).first
        potion_holdings = page.locator(".holdings-panel .subsection").filter(
            has=page.get_by_role("heading", name="Potions")
        ).first
        gem_holdings = page.locator(".holdings-panel .subsection").filter(
            has=page.get_by_role("heading", name="Gems")
        ).first

        with smoke_step(smoke_timing, "sell stackables across holdings and inspect history detail", phase="workbench"):
            lune_row = herb_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Lune stone")
            ).first
            lune_row.get_by_role("button", name="Inspect").click()
            lune_inspector = inspector_item(page, "ingredient:herb:Lune stone")
            expect(lune_inspector).to_be_visible()
            expect(lune_inspector).to_contain_text("Sell Value")
            expect(lune_inspector).to_contain_text(f"{format_gold_amount(lune_sell)}g")

            blessed_row = potion_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Blessed medicine")
            ).first
            blessed_row.get_by_role("button", name="Sell").click()
            expect(toast).to_contain_text("Sold Blessed medicine")
            expect(toast).to_contain_text(f"gain {format_gold_amount(blessed_sell)}g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Blessed medicine")
            expect(page.locator(".history-card .pill", has_text="Potion").first).to_be_visible()
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + blessed_sell)}g"
            expect(
                potion_holdings.locator("tr").filter(has=page.locator("td", has_text="Blessed medicine"))
            ).to_have_count(0)
            page.locator(".history-card").first.locator('button[data-action="inspect-item"]').first.click()
            blessed_inspector = inspector_item(page, "output:potion:Blessed medicine")
            expect(blessed_inspector).to_be_visible()
            expect(blessed_inspector).to_contain_text("Sell Value")
            expect(blessed_inspector).to_contain_text(f"{format_gold_amount(blessed_sell)}g")
            assert "selected" in (page.locator(".history-card").first.get_attribute("class") or "")

            health_row = potion_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Health potion")
            ).first
            health_row.get_by_role("button", name="Sell").click()
            expect(toast).to_contain_text("Sold Health potion")
            expect(toast).to_contain_text(f"gain {format_gold_amount(health_sell)}g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Health potion")
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + blessed_sell + health_sell)}g"
            expect(
                potion_holdings.locator("tr").filter(has=page.locator("td", has_text="Health potion"))
            ).to_have_count(0)
            page.locator(".history-card").first.locator('button[data-action="inspect-item"]').first.click()
            health_inspector = inspector_item(page, "output:potion:Health potion")
            expect(health_inspector).to_be_visible()
            expect(health_inspector).to_contain_text("Recipe only")
            expect(health_inspector).to_contain_text(f"{format_gold_amount(health_sell)}g")
            assert "selected" in (page.locator(".history-card").first.get_attribute("class") or "")

            lune_row = herb_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Lune stone")
            ).first
            lune_row.get_by_role("button", name="Sell").click()
            expect(toast).to_contain_text("Sold Lune stone")
            expect(toast).to_contain_text(f"gain {format_gold_amount(lune_sell)}g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Lune stone")
            expect(page.locator(".history-card .pill", has_text="Ingredient").first).to_be_visible()
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + blessed_sell + health_sell + lune_sell)}g"
            expect(
                herb_holdings.locator("tr").filter(has=page.locator("td", has_text="Lune stone")).first.locator("td").nth(1)
            ).to_have_text("17")

            alexandrite_row = gem_piece_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Alexandrite piece")
            ).first
            alexandrite_row.get_by_role("button", name="Sell").click()
            expect(toast).to_contain_text("Sold Alexandrite piece")
            expect(toast).to_contain_text(f"gain {format_gold_amount(alexandrite_sell)}g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Alexandrite piece")
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + blessed_sell + health_sell + lune_sell + alexandrite_sell)}g"
            expect(
                gem_piece_holdings.locator("tr").filter(
                    has=page.locator("td", has_text="Alexandrite piece")
                ).first.locator("td").nth(1)
            ).to_have_text("5")

            agate_row = gem_holdings.locator("tr").filter(
                has=page.locator("td", has_text="Agate")
            ).first
            agate_row.get_by_role("button", name="Sell").click()
            expect(toast).to_contain_text("Sold Agate")
            expect(toast).to_contain_text(f"gain {format_gold_amount(agate_sell)}g")
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Agate")
            expect(page.locator(".history-card .pill", has_text="Gem").first).to_be_visible()
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + total_sell_gain)}g"
            expect(gem_holdings.locator("tr").filter(has=page.locator("td", has_text="Agate"))).to_have_count(0)
            page.locator(".history-card").first.locator('button[data-action="inspect-item"]').first.click()
            agate_inspector = inspector_item(page, "output:gem:Agate")
            expect(agate_inspector).to_be_visible()
            expect(agate_inspector).to_contain_text("Sell Value")
            expect(agate_inspector).to_contain_text(f"{format_gold_amount(agate_sell)}g")
            assert "selected" in (page.locator(".history-card").first.get_attribute("class") or "")
            assert stat_value(page, "Steps") == "5"

        with smoke_step(smoke_timing, "undo redo and reload sell flow history", phase="persistence"):
            page.locator('button[data-action="undo-action"]').click()
            expect(toast).to_contain_text("Undid Sold Agate")
            assert stat_value(page, "Gold") == (
                f"{format_gold_amount(339 + blessed_sell + health_sell + lune_sell + alexandrite_sell)}g"
            )
            assert stat_value(page, "Gems") == "1"
            expect(gem_holdings.locator("tr").filter(has=page.locator("td", has_text="Agate"))).to_have_count(1)

            page.locator('button[data-action="redo-action"]').click()
            expect(toast).to_contain_text("Redid Sold Agate")
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + total_sell_gain)}g"
            assert stat_value(page, "Gems") == "0"
            expect(gem_holdings.locator("tr").filter(has=page.locator("td", has_text="Agate"))).to_have_count(0)

            reload_page(
                page,
                smoke_timing,
                label="reload after stackable sell flow",
                ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
            )
            assert stat_value(page, "Gold") == f"{format_gold_amount(339 + total_sell_gain)}g"
            assert stat_value(page, "Steps") == "5"
            expect(page.locator(".history-card strong").first).to_contain_text("Sold Agate")
            expect(
                page.locator(".holdings-panel .subsection").filter(
                    has=page.get_by_role("heading", name="Gems")
                ).first.locator("tr").filter(has=page.locator("td", has_text="Agate"))
            ).to_have_count(0)

        context.close()
        browser.close()


def test_index_planner_stackable_preview_and_apply(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        toast = page.locator('[data-role="toast"]')

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner stackable preview page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "configure and preview stackable planner goal", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Stackable Line").click()

            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "stackable", "Blessed medicine")
            set_number_input(line.locator('input[data-action="set-planner-line-quantity"]'), 3)

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Gross Spend") == "120g"
            assert planner_summary_value(page, "Liquidation Recovered") == "0g"
            assert planner_summary_value(page, "Final Gold") == "219g"
            assert planner_summary_value(page, "Steps") == "3"
            assert planner_delta_texts(page) == [
                "Blessed medicine\nMedicine · Potion\n+2",
                "Runic bone\nHerb\n-2",
            ]
            assert planner_step_texts(page) == [
                "1\nBuy Holy water x6\nHoly water is sold this week at 20g each.\n-120g",
                "2\nCraft Blessed medicine\nConsumes Holy water x3, Runic bone x1.\n0g",
                "3\nCraft Blessed medicine\nConsumes Holy water x3, Runic bone x1.\n0g",
            ]

        with smoke_step(smoke_timing, "apply stackable planner preview to workbench", phase="planner"):
            page.get_by_role("button", name="Apply Plan To Workbench").click()

            expect(toast).to_contain_text("Applied plan")
            expect(toast).to_contain_text("2 ordinary simulator actions")
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            assert stat_value(page, "Gold") == "219g"
            assert stat_value(page, "Steps") == "2"
            expect(page.locator(".history-card")).to_have_count(2)
            history_labels = page.locator(".history-card strong").all_inner_texts()
            assert history_labels[:2] == ["Crafted Blessed medicine", "Crafted Blessed medicine"]
            expect(page.locator(".holdings-panel")).to_contain_text("Blessed medicine")

        context.close()
        browser.close()


def test_index_planner_combo_preview_and_apply_preserves_identity(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        toast = page.locator('[data-role="toast"]')

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner combo preview page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "configure and preview combo planner goal", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Combo Line").click()

            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "combo-base", "Bronze ring")
            select_planner_picker_option(line, "combo-gem", "Sapphire", slot=0)

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Gross Spend") == "50g"
            assert planner_summary_value(page, "Final Gold") == "289g"
            assert planner_summary_value(page, "Steps") == "2"
            assert planner_delta_texts(page) == [
                "Bronze ring\nAccessory\n-1",
                "Bronze ring + Sapphire\nAccessory\n+1",
                "Sapphire piece\nGem Piece\n-5",
            ]
            assert planner_step_texts(page) == [
                "1\nCraft Sapphire\nConsumes Sapphire piece x5.\n0g",
                "2\nAssemble Bronze ring with Sapphire\nPays the 50g imbue fee and uses the selected gems.\n-50g",
            ]
            page.locator(".planner-delta-row").filter(
                has=page.locator("strong", has_text="Bronze ring + Sapphire")
            ).first.get_by_role("button", name="Inspect").click()
            expect(page.locator(".planner-inspector-panel")).to_contain_text("Bronze ring")
            expect(page.locator(".planner-inspector-panel")).to_contain_text("Sapphire")

        with smoke_step(smoke_timing, "apply combo planner preview and preserve identity", phase="planner"):
            page.get_by_role("button", name="Apply Plan To Workbench").click()

            expect(toast).to_contain_text("Applied plan")
            expect(toast).to_contain_text("2 ordinary simulator actions")
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            assert stat_value(page, "Gold") == "289g"
            assert stat_value(page, "Steps") == "2"
            ring_card = holdings_gear_card(page, "ring-bronze-1")
            expect(ring_card).to_be_visible()
            expect(ring_card).to_contain_text("Sockets: Sapphire")
            expect(page.locator('[data-holdings-gear-card="bronze-ring-1"]')).to_have_count(0)
            assert page.locator(".history-card strong").all_inner_texts()[:2] == [
                "Assembled Bronze ring",
                "Crafted Sapphire",
            ]

        context.close()
        browser.close()


def test_index_planner_mixed_cross_system_plan_and_apply(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    workbench = default_workbench_state(scenario)
    workbench["ingredients"]["Batta berry"] = 0
    workbench["ingredients"]["Jhi fruit"] = 0
    workbench["equipment"] = [
        instance
        for instance in workbench["equipment"]
        if instance["base_name"] != "Basic Iron Shield"
    ]
    saved_state = build_saved_state(
        scenario,
        workbench=workbench,
        planner={
            "repurposable_equipment_ids": {"boots-leather-1": True},
            "ingredient_keep_counts": {},
            "pinned_output_reserves": {},
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, saved_state)
        page = context.new_page()
        toast = page.locator('[data-role="toast"]')

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load mixed planner flow page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "configure and preview mixed cross-system planner goal", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()

            page.get_by_role("button", name="Add Equipment Line").click()
            equipment_line = page.locator("[data-planner-line]").nth(0)
            select_planner_picker_option(equipment_line, "equipment", "Basic Iron Shield")

            page.get_by_role("button", name="Add Stackable Line").click()
            stackable_line = page.locator("[data-planner-line]").nth(1)
            select_planner_picker_option(stackable_line, "stackable", "Super potion")
            set_number_input(
                stackable_line.locator('input[data-action="set-planner-line-quantity"]'),
                2,
            )

            page.get_by_role("button", name="Add Combo Line").click()
            combo_line = page.locator("[data-planner-line]").nth(2)
            select_planner_picker_option(combo_line, "combo-base", "Bronze ring")
            select_planner_picker_option(combo_line, "combo-gem", "Moonstone", slot=0)

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Gross Spend") == "350g"
            liquidation_recovered = planner_summary_value(page, "Liquidation Recovered")
            assert float(liquidation_recovered.removesuffix("g")) > 0
            delta_rows = planner_delta_texts(page)
            assert "Basic Iron Shield\nEquipment\n+1" in delta_rows
            assert "Bronze ring\nAccessory\n-1" in delta_rows
            assert "Bronze ring + Moonstone\nAccessory\n+1" in delta_rows
            assert "Moonstone piece\nGem Piece\n-5" in delta_rows
            assert "Super potion\nPotion · Potion\n+2" in delta_rows
            assert not any(row.startswith("Silver Talisman\n") for row in delta_rows)
            steps = planner_step_texts(page)
            assert any(step.startswith("1\nSell ") or "\nSell " in step for step in steps)
            assert all("Sell Leather Shoes" not in step for step in steps)
            assert any(
                step.endswith("Craft Moonstone\nConsumes Moonstone piece x5.\n0g")
                for step in steps
            )
            assert any(
                step.endswith(
                    "Buy Super potion x2\nSuper potion is sold this week at 135g each.\n-270g"
                )
                for step in steps
            )
            assert any(
                step.endswith(
                    "Buy Basic Iron Shield\nBasic Iron Shield is sold this week for 30g.\n-30g"
                )
                for step in steps
            )
            assert any(
                step.endswith(
                    "Assemble Bronze ring with Moonstone\nPays the 50g imbue fee and uses the selected gems.\n-50g"
                )
                for step in steps
            )

        with smoke_step(smoke_timing, "apply mixed planner preview to workbench", phase="planner"):
            page.get_by_role("button", name="Apply Plan To Workbench").click()

            expect(toast).to_contain_text("Applied plan")
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            assert float(stat_value(page, "Gold").removesuffix("g")) >= 0
            expect(page.locator('[data-holdings-gear-card="boots-leather-1"]')).to_have_count(1)
            expect(holdings_gear_card(page, "basic-iron-shield-1")).to_contain_text("Basic Iron Shield")
            expect(holdings_gear_card(page, "ring-bronze-1")).to_contain_text("Sockets: Moonstone")
            history_labels = page.locator(".history-card strong").all_inner_texts()
            assert history_labels[:5] == [
                "Assembled Bronze ring",
                "Bought Basic Iron Shield",
                "Bought Super potion",
                "Bought Super potion",
                "Crafted Moonstone",
            ]
            assert "Sold Leather Shoes" not in history_labels[:8]

        context.close()
        browser.close()


def test_index_planner_solved_preview_omits_protected_footer_and_unaffected_equipment(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load solved preview omission page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "preview solved plan without protected footer noise", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()

            page.get_by_role("button", name="Add Equipment Line").click()
            equipment_line = page.locator("[data-planner-line]").nth(0)
            select_planner_picker_option(equipment_line, "equipment", "Leather Shoes")
            set_number_input(
                equipment_line.locator('input[data-action="set-planner-line-quantity"]'),
                8,
            )

            page.get_by_role("button", name="Add Stackable Line").click()
            stackable_line = page.locator("[data-planner-line]").nth(1)
            select_planner_picker_option(stackable_line, "stackable", "Brew of the Master")

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            expect(page.locator(".note-stack")).to_have_count(0)
            delta_rows = planner_delta_texts(page)
            assert "Leather Shoes\nEquipment\n+7" in delta_rows
            assert "Brew of the Master\nBrew · Potion\n+1" in delta_rows
            assert not any(row.startswith("Silver Talisman\n") for row in delta_rows)
            assert not any(row.startswith("Bronze ring\n") for row in delta_rows)
            assert not any(row.startswith("Basic Iron Shield\n") for row in delta_rows)

        context.close()
        browser.close()


def test_index_planner_balances_herb_liquidation_within_cohort(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    workbench = default_workbench_state(scenario)
    workbench["gold"] = 0
    workbench["equipment"] = [
        instance
        for instance in workbench["equipment"]
        if instance["base_name"] != "Silver Talisman"
    ]
    saved_state = build_saved_state(
        scenario,
        workbench=workbench,
        planner={
            "repurposable_equipment_ids": {},
            "ingredient_keep_counts": keep_all_ingredients_except(
                workbench, {"Lune stone", "Nappa grass"}
            ),
            "pinned_output_reserves": {},
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load herb liquidation planner page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "preview herb liquidation within cohort", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Equipment Line").click()
            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "equipment", "Silver Talisman")

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            steps = planner_step_texts(page)
            assert any("Sell Lune stone x16" in step for step in steps)
            assert any("Sell Nappa grass x10" in step for step in steps)
            assert all("Sell Lune stone x26" not in step for step in steps)
            assert all("Sell Yon nut" not in step for step in steps)

        context.close()
        browser.close()


def test_index_planner_balances_gem_piece_liquidation_within_cohort(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    workbench = default_workbench_state(scenario)
    workbench["gold"] = 0
    saved_state = build_saved_state(
        scenario,
        workbench=workbench,
        planner={
            "repurposable_equipment_ids": {},
            "ingredient_keep_counts": keep_all_ingredients_except(
                workbench, {"Alexandrite piece", "Moonstone piece"}
            ),
            "pinned_output_reserves": {},
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load gem liquidation planner page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "preview gem-piece liquidation within cohort", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Equipment Line").click()
            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "equipment", "Leather Shoes")
            set_number_input(
                line.locator('input[data-action="set-planner-line-quantity"]'),
                3,
            )

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            steps = planner_step_texts(page)
            assert any("Sell Alexandrite piece x6" in step for step in steps)
            assert any("Sell Moonstone piece x4" in step for step in steps)
            assert all("Sell Moonstone piece x10" not in step for step in steps)
            assert all("Sell Garnet piece" not in step for step in steps)

        context.close()
        browser.close()


def test_index_planner_ingredient_funding_respects_reserves(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    workbench = default_workbench_state(scenario)
    workbench["gold"] = 82
    workbench["equipment"] = [
        instance
        for instance in workbench["equipment"]
        if instance["base_name"] != "Silver Talisman"
    ]
    saved_state = build_saved_state(
        scenario,
        workbench=workbench,
        planner={
            "repurposable_equipment_ids": {},
            "ingredient_keep_counts": {"Batta berry": 5},
            "pinned_output_reserves": {"Moonstone": 1, "Blessed medicine": 1},
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, saved_state)
        page = context.new_page()
        toast = page.locator('[data-role="toast"]')

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load reserve-respecting funding page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "preview ingredient funding with reserves", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Equipment Line").click()
            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "equipment", "Silver Talisman")

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Gross Spend") == "130g"
            assert planner_summary_value(page, "Liquidation Recovered") == "50g"
            assert planner_summary_value(page, "Final Gold") == "2g"
            delta_rows = planner_delta_texts(page)
            assert "Silver Talisman\nAccessory\n+1" in delta_rows
            assert all("Batta berry" not in row for row in delta_rows)
            assert all("Moonstone piece" not in row for row in delta_rows)
            steps = planner_step_texts(page)
            assert steps
            assert steps[0].startswith("1\nSell ")
            assert all("Batta berry" not in step for step in steps)
            assert all("Moonstone piece" not in step for step in steps)
            assert steps[-1].endswith(
                "Buy Silver Talisman\nSilver Talisman is sold this week for 130g.\n-130g"
            )
            expect(page.locator(".note-stack")).to_have_count(0)

        with smoke_step(smoke_timing, "apply reserve-respecting planner preview", phase="planner"):
            page.get_by_role("button", name="Apply Plan To Workbench").click()

            expect(toast).to_contain_text("Applied plan")
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            assert stat_value(page, "Gold") == "2g"
            expect(holdings_gear_card(page, "silver-talisman-1")).to_contain_text("Silver Talisman")

        context.close()
        browser.close()


def test_index_planner_pure_equipment_goal_uses_ingredient_funding(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load pure equipment funding page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "preview pure equipment goal with ingredient funding", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Equipment Line").click()
            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "equipment", "Leather Shoes")
            set_number_input(
                line.locator('input[data-action="set-planner-line-quantity"]'),
                11,
            )

            page.get_by_role("button", name="Preview Plan").click()

            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")
            assert planner_summary_value(page, "Gross Spend") == "500g"
            liquidation_recovered = planner_summary_value(page, "Liquidation Recovered")
            assert float(liquidation_recovered.removesuffix("g")) > 0

            steps = planner_step_texts(page)
            assert steps
            assert steps[0].startswith("1\nSell ")
            assert steps[-1].endswith(
                "Buy Leather Shoes x10\nLeather Shoes is sold this week for 50g.\n-500g"
            )

        context.close()
        browser.close()


def test_index_planner_blocked_combo_and_repurposable_disassembly(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        blocked_context = browser.new_context()
        blocked = blocked_context.new_page()
        load_index(
            blocked,
            index_url,
            smoke_timing,
            label="load blocked combo planner page",
            ready=lambda: expect(blocked.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "preview blocked combo request", phase="planner"):
            blocked.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            blocked.get_by_role("button", name="Add Combo Line").click()
            planner_scope_button(blocked, "all").click()
            blocked_line = blocked.locator("[data-planner-line]").first
            select_planner_picker_option(blocked_line, "combo-base", "Bronze necklace")
            select_planner_picker_option(blocked_line, "combo-gem", "Ruby", slot=0)
            select_planner_picker_option(blocked_line, "combo-gem", "Sapphire", slot=1)
            select_planner_picker_option(blocked_line, "combo-gem", "Moonstone", slot=2)
            blocked.get_by_role("button", name="Preview Plan").click()
            expect(blocked.locator('[data-planner-status="blocked"]')).to_contain_text(
                "Bronze necklace is blocked because the base accessory is neither owned nor sold this week."
            )
            expect(blocked.locator(".plan-step")).to_have_count(0)

        repurpose_workbench = default_workbench_state(scenario)
        repurpose_workbench["equipment"] = [
            (
                {**instance, "socketed_gems": ["Sapphire"]}
                if instance["id"] == "ring-bronze-1"
                else instance
            )
            for instance in repurpose_workbench["equipment"]
        ]
        repurpose_state = build_saved_state(scenario, workbench=repurpose_workbench)

        repurpose_context = browser.new_context()
        seed_local_storage(repurpose_context, repurpose_state)
        repurpose = repurpose_context.new_page()
        load_index(
            repurpose,
            index_url,
            smoke_timing,
            label="load repurpose planner page",
            ready=lambda: expect(repurpose.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "compare combo preview before and after repurpose rule", phase="planner"):
            repurpose.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            repurpose.get_by_role("button", name="Add Combo Line").click()
            repurpose_line = repurpose.locator("[data-planner-line]").first
            select_planner_picker_option(repurpose_line, "combo-base", "Bronze ring")
            select_planner_picker_option(repurpose_line, "combo-gem", "Moonstone", slot=0)
            repurpose.get_by_role("button", name="Preview Plan").click()

            assert planner_summary_value(repurpose, "Gross Spend") == "90g"
            expect(repurpose.locator(".plan-steps")).to_contain_text("Buy Bronze ring")

            repurpose.locator(
                'input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]'
            ).check()
            expect(repurpose.locator('[data-planner-status="draft"]')).to_contain_text(
                "Preview required"
            )
            repurpose.get_by_role("button", name="Preview Plan").click()

            assert planner_summary_value(repurpose, "Gross Spend") == "50g"
            expect(repurpose.locator(".plan-steps")).to_contain_text("Disassemble Bronze ring")
            expect(repurpose.locator(".plan-steps")).not_to_contain_text("Buy Bronze ring")

        repurpose_context.close()
        blocked_context.close()
        browser.close()


def test_index_planner_rules_persist_reload_and_reset(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load planner rules persistence page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "configure planner rules and preview before reload", phase="planner"):
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            page.get_by_role("button", name="Add Stackable Line").click()
            line = page.locator("[data-planner-line]").first
            select_planner_picker_option(line, "stackable", "Blessed medicine")
            set_number_input(line.locator('input[data-action="set-planner-line-quantity"]'), 3)
            page.locator(
                'input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]'
            ).check()
            set_number_input(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]'),
                5,
            )
            set_number_input(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]'),
                1,
            )
            page.get_by_role("button", name="Preview Plan").click()
            expect(page.locator('[data-planner-status="solved"]')).to_contain_text("Solution found")

        with smoke_step(smoke_timing, "reload planner rules and clear them via reset and imports", phase="persistence"):
            reload_page(
                page,
                smoke_timing,
                label="reload planner rules page",
                ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
            )
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            expect(
                page.locator('input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]')
            ).to_be_checked()
            expect(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]')
            ).to_have_value("5")
            expect(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]')
            ).to_have_value("1")
            expect(page.locator("[data-planner-line]")).to_have_count(0)
            expect(page.locator(".plan-step")).to_have_count(0)
            expect(page.locator('[data-planner-status="draft"]')).to_contain_text("No plan yet")

            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            page.locator('button[data-action="reset-workbench"]').click()
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            expect(
                page.locator('input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]')
            ).not_to_be_checked()
            expect(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]')
            ).to_have_value("0")
            expect(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]')
            ).to_have_value("0")

            page.locator(
                'input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]'
            ).check()
            set_number_input(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]'),
                4,
            )
            set_number_input(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]'),
                2,
            )
            page.locator('button[data-action="apply-base-to-workbench"]').dispatch_event("click")
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            expect(
                page.locator('input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]')
            ).not_to_be_checked()
            expect(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]')
            ).to_have_value("0")
            expect(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]')
            ).to_have_value("0")

            page.locator(
                'input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]'
            ).check()
            set_number_input(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]'),
                6,
            )
            set_number_input(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]'),
                3,
            )
            page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
            set_data_json(page, scenario)
            page.locator('button[data-action="import-scenario-json"]').click()
            page.locator('button[data-action="switch-tab"][data-tab="planner"]').click()
            expect(
                page.locator('input[data-action="toggle-planner-repurpose"][data-id="ring-bronze-1"]')
            ).not_to_be_checked()
            expect(
                page.locator('input[data-action="set-planner-keep-count"][data-name="Batta berry"]')
            ).to_have_value("0")
            expect(
                page.locator('input[data-action="set-planner-pinned-output"][data-name="Moonstone"]')
            ).to_have_value("0")
            expect(page.locator("[data-planner-line]")).to_have_count(0)
            expect(page.locator(".plan-step")).to_have_count(0)

        context.close()
        browser.close()


def test_index_rejects_invalid_import_json(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    alias_payload = load_seed_scenario()
    alias_payload["for_sale"]["outputs"]["dark toxin"] = True
    del alias_payload["for_sale"]["outputs"]["Dark Toxin"]

    misbucket_payload = load_seed_scenario()
    misbucket_payload["inventory"]["gems"]["Health potion"] = 1

    bad_market_payload = load_seed_scenario()
    bad_market_payload["market"]["sell_markdown"] = 1.5

    bad_equipment_payload = load_seed_scenario()
    bad_equipment_payload["equipment"]["definitions"]["Traveler ring"] = {
        "name": "Traveler ring",
        "family": "ring",
        "source_sheet": "Accessories",
        "rank": "",
        "buy_price": 40,
        "max_hp": None,
        "stats": {},
        "effects": [],
    }

    obsolete_optimizer_payload = load_seed_scenario()
    obsolete_optimizer_payload["equipment"]["definitions"]["Bronze ring"]["optimizer_auto_sell"] = True

    bad_inventory_equipment_payload = load_seed_scenario()
    bad_inventory_equipment_payload["equipment"]["definitions"]["Traveler ring"] = {
        "name": "Traveler ring",
        "family": "ring",
        "category": "accessory",
        "rank": "",
        "buy_price": 40,
        "max_hp": None,
        "stats": {},
        "effects": [],
    }
    bad_inventory_equipment_payload["inventory"]["equipment"] = [
        {
            "id": "ring-1",
            "base_name": "Missing ring",
            "current_hp": None,
        }
    ]

    bad_inventory_equipment_hp_payload = load_seed_scenario()
    bad_inventory_equipment_hp_payload["inventory"]["equipment"][1]["current_hp"] = None

    bad_for_sale_equipment_payload = load_seed_scenario()
    bad_for_sale_equipment_payload["for_sale"]["equipment"]["Missing ring"] = True

    bad_non_socketable_combo_payload = load_seed_scenario()
    bad_non_socketable_combo_payload["inventory"]["equipment"][1]["socketed_gems"] = ["Sapphire"]

    bad_socket_cap_payload = load_seed_scenario()
    bad_socket_cap_payload["inventory"]["equipment"][0]["socketed_gems"] = ["Sapphire", "Ruby"]

    bad_socket_unknown_gem_payload = load_seed_scenario()
    bad_socket_unknown_gem_payload["inventory"]["equipment"][0]["socketed_gems"] = ["Missing gem"]

    valid_duplicate_socket_payload = load_seed_scenario()
    valid_duplicate_socket_payload["inventory"]["equipment"][0] = {
        "id": "ring-bronze-1",
        "base_name": "Bronze necklace",
        "current_hp": None,
        "socketed_gems": ["Ruby", "Ruby"],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        dialog_messages: list[str] = []
        page.on("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.dismiss()))

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load invalid import validation page",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "reject aliased output and misbucketed inventory imports", phase="validation"):
            page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, alias_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert dialog_messages
            assert 'unknown name "dark toxin"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            expect(page.locator('[data-recipe-card="Warming medicine"]')).to_be_visible()

            page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
            set_data_json(page, misbucket_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'unknown name "Health potion"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            expect(page.locator('[data-recipe-card="Warming medicine"]')).to_be_visible()

        with smoke_step(smoke_timing, "reject malformed market equipment and socket payloads", phase="validation"):
            page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
            set_data_json(page, bad_market_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'sell_markdown must not exceed 1' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_equipment_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'missing "category"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, obsolete_optimizer_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'unknown key "optimizer_auto_sell"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_inventory_equipment_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'unknown equipment "Missing ring"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_inventory_equipment_hp_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert "current_hp is required" in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_for_sale_equipment_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'for_sale.equipment references unknown name "Missing ring"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_non_socketable_combo_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert "socketed_gems is only allowed for equipment with socket_policy" in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_socket_cap_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert "socketed_gems must not exceed 1 gems" in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

            set_data_json(page, bad_socket_unknown_gem_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert 'references unknown gem "Missing gem"' in dialog_messages[-1]
            expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()

        with smoke_step(smoke_timing, "accept valid duplicate socket import after failures", phase="validation"):
            prior_dialog_count = len(dialog_messages)
            set_data_json(page, valid_duplicate_socket_payload)
            page.locator('button[data-action="import-scenario-json"]').click()
            assert len(dialog_messages) == prior_dialog_count
            page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
            expect(accessory_holdings_section(page)).to_contain_text("Bronze necklace")

        context.close()
        browser.close()


def test_index_ignores_legacy_v2_saved_state(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, "not valid json", key=LEGACY_STORAGE_KEY)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load page with legacy v2 saved state present",
            ready=lambda: expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible(),
        )

        with smoke_step(smoke_timing, "ignore legacy v2 saved state", phase="validation"):
            expect(page.locator('[data-role="fatal-state"]')).to_have_count(0)
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
            assert stat_value(page, "Gold") == "339g"
            expect(page.locator('[data-recipe-card="Warming medicine"]')).to_be_visible()

        context.close()
        browser.close()


def test_index_blocks_invalid_saved_state_and_can_clear(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    invalid_saved_state = {
        "scenario": scenario,
        "workbench": {
            "gold": scenario["inventory"]["gold"],
            "ingredients": scenario["inventory"]["ingredients"],
            "potions": scenario["inventory"]["potions"],
            "gems": scenario["inventory"]["gems"],
            "equipment": scenario["inventory"]["equipment"],
        },
        "history": [
            {
                "label": "Legacy snapshot",
                "snapshot": {
                    "gold": scenario["inventory"]["gold"],
                    "ingredients": scenario["inventory"]["ingredients"],
                    "potions": scenario["inventory"]["potions"],
                    "gems": scenario["inventory"]["gems"],
                    "equipment": scenario["inventory"]["equipment"],
                },
                "after": None,
                "effect": None,
            }
        ],
        "redo": [],
        "planner": default_planner_state(),
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, invalid_saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load page with invalid saved state",
            ready=lambda: expect(page.locator('[data-role="fatal-state"]')).to_be_visible(),
        )

        with smoke_step(smoke_timing, "show and clear invalid saved state blocker", phase="validation"):
            fatal_state = page.locator('[data-role="fatal-state"]')
            expect(fatal_state).to_be_visible()
            expect(fatal_state).to_contain_text("Saved Data Blocked")
            expect(fatal_state).to_contain_text('missing "before"')

            page.locator('button[data-action="clear-invalid-local-data"]').click()

            expect(page.locator('[data-role="fatal-state"]')).to_have_count(0)
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
            expect(page.locator('[data-recipe-card="Warming medicine"]')).to_be_visible()

        context.close()
        browser.close()


def test_index_blocks_legacy_effect_saved_state_and_can_clear(smoke_timing) -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()
    scenario = load_seed_scenario()
    base_workbench = {
        "gold": scenario["inventory"]["gold"],
        "ingredients": scenario["inventory"]["ingredients"],
        "potions": scenario["inventory"]["potions"],
        "gems": scenario["inventory"]["gems"],
        "equipment": scenario["inventory"]["equipment"],
    }
    invalid_saved_state = {
        "scenario": scenario,
        "workbench": base_workbench,
        "history": [
            {
                "label": "Legacy effect payload",
                "before": base_workbench,
                "after": base_workbench,
                "effect": {
                    "gold": -45,
                    "used": [],
                    "autoBought": [],
                    "outputs": [],
                },
            }
        ],
        "redo": [],
        "planner": default_planner_state(),
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        seed_local_storage(context, invalid_saved_state)
        page = context.new_page()

        load_index(
            page,
            index_url,
            smoke_timing,
            label="load page with legacy effect saved state",
            ready=lambda: expect(page.locator('[data-role="fatal-state"]')).to_be_visible(),
        )

        with smoke_step(smoke_timing, "show and clear legacy effect blocker", phase="validation"):
            fatal_state = page.locator('[data-role="fatal-state"]')
            expect(fatal_state).to_be_visible()
            expect(fatal_state).to_contain_text("Saved Data Blocked")
            expect(fatal_state).to_contain_text('missing "transactions"')

            page.locator('button[data-action="clear-invalid-local-data"]').click()

            expect(page.locator('[data-role="fatal-state"]')).to_have_count(0)
            expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
            expect(page.locator('[data-recipe-card="Warming medicine"]')).to_be_visible()

        context.close()
        browser.close()

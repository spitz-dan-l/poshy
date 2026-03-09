from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
STORAGE_KEY = "poshy.single-file.lab.v2"


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
    return page.locator(f'[data-inspector-item="{key}"]')


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


def test_index_smoke() -> None:
    index_url = (REPO_ROOT / "index.html").resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(index_url, wait_until="domcontentloaded")

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
        expect(page.locator(".inspector-panel")).to_have_attribute(
            "data-selected-detail-key", "output:gem:Agate"
        )
        expect(page.locator(".inspector-panel")).not_to_contain_text("Inspecting")

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

        page.locator('button[data-action="switch-tab"][data-tab="shop"]').click()
        expect(page.get_by_role("heading", name="Direct Buy Potions")).to_be_visible()
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

        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        click_workbench_category(page, "accessories")
        expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_be_visible()

        page.locator('button[data-action="switch-tab"][data-tab="inventory"]').click()
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

        page.locator('button[data-action="apply-base-to-workbench"]').dispatch_event("click")
        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
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

        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
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

        page.locator('button[data-action="switch-tab"][data-tab="recipes"]').click()
        expect(page.get_by_role("heading", name="Catalog")).to_be_visible()
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

        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        assert stat_value(page, "Gold") == "343.86g"
        expect(page.locator('[data-holdings-gear-card="boots-leather-1"]')).to_have_count(0)
        page.locator('button[data-action="switch-tab"][data-tab="recipes"]').click()
        bronze_ring_definition = page.locator("details.recipe-card").filter(
            has=page.locator("summary strong", has_text="Bronze ring")
        ).first
        bronze_ring_definition.locator("summary").click()
        expect(bronze_ring_definition).not_to_contain_text("Auto-sell in optimizer")

        mobile_context = browser.new_context(
            viewport={"width": 430, "height": 932},
            is_mobile=True,
            device_scale_factor=2,
        )
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
        expect(mobile.locator('[data-role="mobile-inspector"]')).to_have_count(0)

        mobile_holdings_button.click()
        expect(mobile.get_by_role("heading", name="Current Holdings")).to_be_visible()
        expect(mobile.get_by_role("heading", name="Alchemy Workbench")).not_to_be_visible()

        mobile_log_button.click()
        expect(mobile.get_by_role("heading", name="Action Log")).to_be_visible()
        expect(mobile.get_by_role("heading", name="Current Holdings")).not_to_be_visible()

        mobile_workbench_button.click()
        mobile_holdings_button.click()
        holdings_gear_card(mobile, "boots-leather-1").get_by_role("button", name="Inspect").click()
        mobile_sheet = mobile.locator('[data-role="mobile-inspector"]')
        expect(mobile_sheet).to_be_visible()
        expect(mobile.get_by_role("heading", name="Current Holdings")).to_be_visible()
        expect(mobile_sheet).to_contain_text("Leather Shoes")
        expect(mobile_sheet.locator('[data-inspector-item="equipment_instance:boots-leather-1"]')).to_contain_text(
            "7/7"
        )
        expect(mobile_sheet).not_to_contain_text("boots-leather-1")
        mobile_sheet.get_by_role("button", name="Close", exact=True).click()
        expect(mobile.locator('[data-role="mobile-inspector"]')).to_have_count(0)

        hero_toggle.click()
        expect(hero_toggle).to_have_text("Hide Intro")
        expect(mobile.locator(".status-stack")).to_be_visible()

        mobile_context.close()
        context.close()
        browser.close()


def test_index_preserves_scroll_positions() -> None:
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

        page.goto(index_url, wait_until="domcontentloaded")
        page.locator('button[data-action="switch-tab"][data-tab="data"]').click()
        expect(page.get_by_role("heading", name="Data Studio")).to_be_visible()
        set_data_json(page, modified_scenario)
        page.locator('button[data-action="import-scenario-json"]').click()

        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()

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
            page.locator(".inspector-panel .inspector-scroll"),
            lambda: page.locator(
                'button[data-action="sell-stackable"][data-bucket="ingredients"][data-name="Lune stone"]'
            ).dispatch_event("click"),
            label="inspector panel",
            requested_position=280,
        )

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

        page.set_viewport_size({"width": 430, "height": 932})
        page.wait_for_timeout(50)
        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        holdings_button = page.locator(
            'button[data-action="set-workbench-mobile-section"][data-section="holdings"]'
        )
        expect(holdings_button).to_be_visible()
        holdings_button.click()
        holdings_gear_card(page, "ring-bronze-1").get_by_role("button", name="Inspect").click()
        mobile_sheet = page.locator(".mobile-inspector-sheet")
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


def test_index_accessory_combo_assembly() -> None:
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

        page.goto(index_url, wait_until="domcontentloaded")

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


def test_index_stackable_sell_flows() -> None:
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

        page.goto(index_url, wait_until="domcontentloaded")
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

        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
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


def test_index_rejects_invalid_import_json() -> None:
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

        page.goto(index_url, wait_until="domcontentloaded")
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

        prior_dialog_count = len(dialog_messages)
        set_data_json(page, valid_duplicate_socket_payload)
        page.locator('button[data-action="import-scenario-json"]').click()
        assert len(dialog_messages) == prior_dialog_count
        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        expect(accessory_holdings_section(page)).to_contain_text("Bronze necklace")

        context.close()
        browser.close()


def test_index_blocks_invalid_saved_state_and_can_clear() -> None:
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
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script(
            f"window.localStorage.setItem({json.dumps(STORAGE_KEY)}, {json.dumps(json.dumps(invalid_saved_state))});"
        )
        page = context.new_page()

        page.goto(index_url, wait_until="domcontentloaded")

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


def test_index_blocks_legacy_effect_saved_state_and_can_clear() -> None:
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
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script(
            f"window.localStorage.setItem({json.dumps(STORAGE_KEY)}, {json.dumps(json.dumps(invalid_saved_state))});"
        )
        page = context.new_page()

        page.goto(index_url, wait_until="domcontentloaded")

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

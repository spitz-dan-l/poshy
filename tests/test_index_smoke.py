from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
STORAGE_KEY = "poshy.single-file.lab.v1"


def load_seed_scenario() -> dict:
    return json.loads((REPO_ROOT / "data/seed_scenario.json").read_text(encoding="utf-8"))


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
        expect(page.get_by_role("heading", name="Equipment Market")).to_be_visible()
        expect(page.locator(".holdings-panel").get_by_role("heading", name="Equipment")).to_be_visible()
        expect(page.locator(".holdings-panel").get_by_role("heading", name="Potions")).to_be_visible()
        expect(page.locator(".holdings-panel").get_by_role("heading", name="Gems")).to_be_visible()
        expect(page.locator(".holdings-panel")).to_contain_text("Health potion")
        expect(page.locator(".holdings-panel")).to_contain_text("Bronze ring")
        expect(page.locator(".holdings-panel")).to_contain_text("Basic Iron Shield")
        assert stat_value(page, "Equipment") == "4"
        assert stat_value(page, "Gems") == "0"

        agate_card = page.locator(".workbench-panel .potion-card").filter(
            has=page.locator("h3", has_text="Agate")
        ).first
        expect(agate_card).to_be_visible()
        expect(agate_card.locator(".potion-meta-line")).to_contain_text("Gem")
        expect(agate_card.locator(".potion-meta-line")).to_contain_text("Violet")
        expect(agate_card.locator(".potion-meta-line")).to_contain_text("golem +")
        expect(agate_card.locator(".potion-meta-line")).not_to_contain_text("Tier")

        warming_card = page.locator('[data-recipe-card="Warming medicine"]')
        expect(warming_card).to_be_visible()
        expect(warming_card.locator(".potion-meta-line")).to_contain_text("Tier D")
        expect(warming_card.locator(".potion-meta-line")).to_contain_text("Medicine")
        warming_card.get_by_role("button", name="Inspect").click()
        warming_inspector = page.locator('[data-inspector-recipe="Warming medicine"]')
        expect(warming_inspector).to_be_visible()
        expect(warming_inspector).to_contain_text("Reactive")
        expect(warming_inspector).to_contain_text("Resets Temp to 0 from a negative number")
        agate_card.get_by_role("button", name="Inspect").click()
        agate_inspector = page.locator('[data-inspector-recipe="Agate"]')
        expect(agate_inspector).to_be_visible()
        expect(agate_inspector).to_contain_text("Violet")
        expect(agate_inspector).to_contain_text("golem +")
        expect(agate_inspector).to_contain_text("gain 2MP every turn you don't cast a spell")
        expect(page.locator(".inspector-panel")).to_have_attribute("data-selected-recipe", "Agate")
        expect(page.locator(".inspector-panel")).not_to_contain_text("Inspecting")

        workbench_content = page.locator(".workbench-panel .workbench-content")
        scroll_metrics = workbench_content.evaluate(
            "(el) => ({ clientHeight: Math.round(el.clientHeight), scrollHeight: Math.round(el.scrollHeight) })"
        )
        assert scroll_metrics["scrollHeight"] > scroll_metrics["clientHeight"]
        workbench_content.hover()
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(50)
        assert workbench_content.evaluate("el => Math.round(el.scrollTop)") > 0
        scrolled_top = workbench_content.evaluate(
            "(el) => { el.scrollTop = 280; return Math.round(el.scrollTop); }"
        )
        page.locator(
            '[data-recipe-card="Ancient medicine"] button[data-action="inspect-recipe"]'
        ).dispatch_event("click")
        assert workbench_content.evaluate("el => Math.round(el.scrollTop)") == scrolled_top

        holdings_health_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="Health potion")
        ).first
        expect(holdings_health_row.get_by_role("button", name="Inspect")).to_have_count(1)
        holdings_health_row.get_by_role("button", name="Inspect").click()
        expect(page.locator('[data-inspector-recipe="Health potion"]')).to_be_visible()

        core_holdings = page.locator(".holdings-panel .subsection").filter(
            has=page.get_by_role("heading", name="Herbs")
        ).first
        gem_piece_holdings = page.locator(".holdings-panel .subsection").filter(
            has=page.get_by_role("heading", name="Gem Pieces")
        ).first
        expect(core_holdings).to_contain_text("Ibsidian shard")
        expect(gem_piece_holdings).not_to_contain_text("Ibsidian shard")

        ancient_card = page.locator('[data-recipe-card="Ancient medicine"]')
        expect(ancient_card).to_be_visible()
        expect(ancient_card).to_contain_text("Direct buy is not sold on this level.")
        expect(ancient_card.locator('button[data-action="buy-once"]')).to_be_disabled()

        mana_card = page.locator('[data-recipe-card="Mana potion"]')
        expect(mana_card).to_be_visible()
        expect(mana_card.locator('button[data-action="buy-once"]')).to_be_enabled()
        expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze ring"]')).to_be_visible()
        expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_have_count(0)

        initial_gold = stat_value(page, "Gold")

        craft_button = page.locator(
            'button[data-action="craft-once"]:not([disabled])'
        ).first
        expect(craft_button).to_be_visible()
        craft_button.click()

        expect(page.locator('[data-role="toast"]')).to_contain_text("Crafted")
        expect(page.locator(".history-card strong").first).to_contain_text("Crafted")
        expect(page.locator('button[data-action="undo-action"]')).to_contain_text("Crafted")
        history_inspect_button = page.locator(".history-card").first.locator('button[data-action="inspect-recipe"]').first
        expect(history_inspect_button).to_have_count(1)
        selected_history_recipe = history_inspect_button.get_attribute("data-recipe")
        assert selected_history_recipe
        history_inspect_button.click()
        expect(page.locator(f'[data-inspector-recipe="{selected_history_recipe}"]')).to_be_visible()
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
        expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_be_visible()

        page.locator('button[data-action="switch-tab"][data-tab="inventory"]').click()
        base_gold_input = page.locator("#base-gold")
        updated_gold = str(int(initial_gold.removesuffix("g")) + 7)
        base_gold_input.fill(updated_gold)
        base_gold_input.press("Tab")

        inventory_panel = page.locator('[data-tab-panel="inventory"]')
        expect(inventory_panel.get_by_role("heading", name="Equipment")).to_be_visible()
        expect(inventory_panel.locator('input[data-action="set-base-equipment-name"]')).to_have_count(4)
        boots_hp = inventory_panel.locator(
            'input[data-action="set-base-equipment-hp"][data-id="boots-leather-1"]'
        )
        boots_hp.fill("5")
        boots_hp.press("Tab")

        inventory_panel.locator('button[data-action="add-starting-equipment"]').click()
        expect(inventory_panel.locator('input[data-action="set-base-equipment-name"]')).to_have_count(5)
        added_equipment_name = inventory_panel.locator(
            'input[data-action="set-base-equipment-name"][data-id="ape-1"]'
        )
        expect(added_equipment_name).to_have_value("Ape")
        added_equipment_name.fill("Bronze necklace")
        added_equipment_name.press("Tab")
        added_equipment_row = inventory_panel.locator("tr").filter(
            has=page.locator('code', has_text="ape-1")
        )
        expect(
            inventory_panel.locator('input[data-action="set-base-equipment-name"][data-id="ape-1"]')
        ).to_have_value("Bronze necklace")
        expect(added_equipment_row).to_contain_text("N/A")
        added_equipment_row.get_by_role("button", name="Remove").click()
        expect(inventory_panel.locator('input[data-action="set-base-equipment-name"]')).to_have_count(4)

        page.locator('button[data-action="apply-base-to-workbench"]').dispatch_event("click")
        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        assert stat_value(page, "Gold") == f"{updated_gold}g"
        leather_shoes_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="Leather Shoes")
        ).first
        expect(leather_shoes_row).to_contain_text("5/7")
        expect(leather_shoes_row).to_contain_text("17.86g")
        expect(page.locator('button[data-action="buy-equipment"][data-name="Bronze necklace"]')).to_be_visible()

        page.locator('button[data-action="buy-equipment"][data-name="Bronze ring"]').click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Bought Bronze ring")
        expect(page.locator('[data-role="toast"]')).to_contain_text("spend 40g")
        expect(page.locator(".history-card strong").first).to_contain_text("Bought Bronze ring")
        expect(page.locator(".history-card .pill", has_text="Equipment").first).to_be_visible()
        assert stat_value(page, "Equipment") == "5"
        assert stat_value(page, "Gold") == "306g"
        bought_ring_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="bronze-ring-1")
        ).first
        expect(bought_ring_row).to_contain_text("Bronze ring")

        page.locator('button[data-action="undo-action"]').click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Undid Bought Bronze ring")
        assert stat_value(page, "Equipment") == "4"
        assert stat_value(page, "Gold") == f"{updated_gold}g"
        expect(
            page.locator(".holdings-panel tr").filter(has=page.locator("td", has_text="bronze-ring-1"))
        ).to_have_count(0)

        page.locator('button[data-action="redo-action"]').click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Redid Bought Bronze ring")
        assert stat_value(page, "Equipment") == "5"
        assert stat_value(page, "Gold") == "306g"
        bought_ring_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="bronze-ring-1")
        ).first
        expect(bought_ring_row).to_contain_text("Bronze ring")

        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        assert stat_value(page, "Equipment") == "5"
        assert stat_value(page, "Gold") == "306g"
        bought_ring_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="bronze-ring-1")
        ).first
        expect(bought_ring_row).to_contain_text("Bronze ring")

        bought_ring_row.get_by_role("button", name="Sell").click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Sold Bronze ring")
        expect(page.locator('[data-role="toast"]')).to_contain_text("gain 20g")
        expect(page.locator(".history-card strong").first).to_contain_text("Sold Bronze ring")
        assert stat_value(page, "Equipment") == "4"
        assert stat_value(page, "Gold") == "326g"
        expect(
            page.locator(".holdings-panel tr").filter(has=page.locator("td", has_text="bronze-ring-1"))
        ).to_have_count(0)

        page.locator('button[data-action="undo-action"]').click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Undid Sold Bronze ring")
        assert stat_value(page, "Equipment") == "5"
        assert stat_value(page, "Gold") == "306g"
        bought_ring_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="bronze-ring-1")
        ).first
        expect(bought_ring_row).to_contain_text("Bronze ring")

        page.locator('button[data-action="redo-action"]').click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Redid Sold Bronze ring")
        assert stat_value(page, "Equipment") == "4"
        assert stat_value(page, "Gold") == "326g"
        expect(
            page.locator(".holdings-panel tr").filter(has=page.locator("td", has_text="bronze-ring-1"))
        ).to_have_count(0)

        leather_shoes_row = page.locator(".holdings-panel tr").filter(
            has=page.locator("td", has_text="Leather Shoes")
        ).first
        leather_shoes_row.get_by_role("button", name="Sell").click()
        expect(page.locator('[data-role="toast"]')).to_contain_text("Sold Leather Shoes")
        expect(page.locator('[data-role="toast"]')).to_contain_text("gain 17.86g")
        expect(page.locator(".history-card strong").first).to_contain_text("Sold Leather Shoes")
        assert stat_value(page, "Equipment") == "3"
        assert stat_value(page, "Gold") == "343.86g"
        expect(
            page.locator(".holdings-panel tr").filter(has=page.locator("td", has_text="Leather Shoes"))
        ).to_have_count(0)

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
        auto_sell_toggle = bronze_ring_definition.locator(
            'input[data-action="set-equipment-auto-sell"][data-name="Bronze ring"]'
        )
        expect(auto_sell_toggle).not_to_be_checked()
        auto_sell_toggle.check()
        expect(auto_sell_toggle).to_be_checked()

        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        assert stat_value(page, "Gold") == "343.86g"
        expect(
            page.locator(".holdings-panel tr").filter(has=page.locator("td", has_text="Leather Shoes"))
        ).to_have_count(0)
        page.locator('button[data-action="switch-tab"][data-tab="recipes"]').click()
        bronze_ring_definition = page.locator("details.recipe-card").filter(
            has=page.locator("summary strong", has_text="Bronze ring")
        ).first
        bronze_ring_definition.locator("summary").click()
        expect(
            bronze_ring_definition.locator(
                'input[data-action="set-equipment-auto-sell"][data-name="Bronze ring"]'
            )
        ).to_be_checked()

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
        mobile.locator('[data-recipe-card="Warming medicine"]').get_by_role("button", name="Inspect").click()
        mobile_sheet = mobile.locator('[data-role="mobile-inspector"]')
        expect(mobile_sheet).to_be_visible()
        expect(mobile.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        expect(mobile_sheet).to_contain_text("Warming medicine")
        expect(mobile_sheet.locator('[data-inspector-recipe="Warming medicine"]')).to_contain_text(
            "Resets Temp to 0 from a negative number"
        )
        mobile_sheet.get_by_role("button", name="Close", exact=True).click()
        expect(mobile.locator('[data-role="mobile-inspector"]')).to_have_count(0)

        hero_toggle.click()
        expect(hero_toggle).to_have_text("Hide Intro")
        expect(mobile.locator(".status-stack")).to_be_visible()

        mobile_context.close()
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

    bad_inventory_equipment_payload = load_seed_scenario()
    bad_inventory_equipment_payload["equipment"]["definitions"]["Traveler ring"] = {
        "name": "Traveler ring",
        "family": "ring",
        "source_sheet": "Accessories",
        "rank": "",
        "buy_price": 40,
        "max_hp": None,
        "stats": {},
        "effects": [],
        "optimizer_auto_sell": False,
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
        assert 'missing "optimizer_auto_sell"' in dialog_messages[-1]
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

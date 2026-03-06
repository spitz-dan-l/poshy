from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]


def stat_value(page, label: str) -> str:
    stat = page.locator(f'[data-run-stat="{label}"]')
    expect(stat).to_have_count(1)
    return stat.locator("span").inner_text()


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
        expect(page.locator(".holdings-panel").get_by_role("heading", name="Potions")).to_be_visible()
        expect(page.locator(".holdings-panel").get_by_role("heading", name="Gems")).to_be_visible()
        expect(page.locator(".holdings-panel")).to_contain_text("Health potion")
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
        expect(page.locator(".inspector-panel")).to_contain_text("Inspecting Agate")

        workbench_list = page.locator(".workbench-panel .grid-list")
        scrolled_top = workbench_list.evaluate(
            "(el) => { el.scrollTop = 280; return Math.round(el.scrollTop); }"
        )
        page.locator(
            '[data-recipe-card="Ancient medicine"] button[data-action="inspect-recipe"]'
        ).dispatch_event("click")
        assert workbench_list.evaluate("el => Math.round(el.scrollTop)") == scrolled_top

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
        expect(page.locator('input[data-action="set-ingredient-sale"][data-name="Lune stone"]')).to_be_checked()
        expect(page.locator('input[data-action="set-output-sale"][data-name="Mana potion"]')).to_be_checked()
        expect(page.locator('input[data-action="set-output-sale"][data-name="Ancient medicine"]')).to_have_count(0)
        page.locator('input[data-action="toggle-zero-shop"]').check()
        expect(page.locator('input[data-action="set-output-sale"][data-name="Ancient medicine"]')).not_to_be_checked()

        page.locator('button[data-action="switch-tab"][data-tab="inventory"]').click()
        base_gold_input = page.locator("#base-gold")
        updated_gold = str(int(initial_gold.removesuffix("g")) + 7)
        base_gold_input.fill(updated_gold)
        base_gold_input.press("Tab")

        page.locator(".tools-drawer summary").click()
        page.locator('button[data-action="apply-base-to-workbench"]').click()
        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        expect(page.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        assert stat_value(page, "Gold") == f"{updated_gold}g"

        page.locator('button[data-action="switch-tab"][data-tab="recipes"]').click()
        expect(page.get_by_role("heading", name="Catalog")).to_be_visible()
        expect(page.get_by_role("heading", name="Ingredient Definitions")).to_be_visible()
        recipe_names = page.locator("details.recipe-card summary strong").all_inner_texts()
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
        mobile_details_button = mobile.locator(
            'button[data-action="set-workbench-mobile-section"][data-section="details"]'
        )
        expect(mobile_holdings_button).to_be_visible()
        expect(mobile_log_button).to_be_visible()
        expect(mobile_details_button).to_be_visible()
        expect(mobile.get_by_role("heading", name="Alchemy Workbench")).to_be_visible()
        expect(mobile.get_by_role("heading", name="Current Holdings")).not_to_be_visible()
        expect(mobile.get_by_role("heading", name="Action Log")).not_to_be_visible()
        expect(mobile.get_by_role("heading", name="Item Details")).not_to_be_visible()

        mobile_holdings_button.click()
        expect(mobile.get_by_role("heading", name="Current Holdings")).to_be_visible()
        expect(mobile.get_by_role("heading", name="Alchemy Workbench")).not_to_be_visible()

        mobile_log_button.click()
        expect(mobile.get_by_role("heading", name="Action Log")).to_be_visible()
        expect(mobile.get_by_role("heading", name="Current Holdings")).not_to_be_visible()

        mobile_workbench_button.click()
        mobile.locator('[data-recipe-card="Warming medicine"]').get_by_role("button", name="Inspect").click()
        expect(mobile.get_by_role("heading", name="Item Details")).to_be_visible()
        expect(mobile.get_by_role("heading", name="Alchemy Workbench")).not_to_be_visible()
        expect(mobile.locator('[data-inspector-recipe="Warming medicine"]')).to_contain_text(
            "Resets Temp to 0 from a negative number"
        )

        hero_toggle.click()
        expect(hero_toggle).to_have_text("Hide Intro")
        expect(mobile.locator(".status-stack")).to_be_visible()

        mobile_context.close()
        context.close()
        browser.close()

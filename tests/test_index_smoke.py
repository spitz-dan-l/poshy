from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]


def stat_value(page, label: str) -> str:
    stat = page.locator(".stat-box").filter(has_text=label)
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
        expect(page.get_by_role("heading", name="Potion Workbench")).to_be_visible()

        initial_gold = stat_value(page, "Workbench Gold")

        craft_button = page.locator(
            'button[data-action="craft-once"]:not([disabled])'
        ).first
        expect(craft_button).to_be_visible()
        craft_button.click()

        expect(page.locator(".history-card strong").first).to_contain_text("Crafted")
        assert stat_value(page, "Undo Steps") == "1"

        page.get_by_role("button", name="Undo Last Action").click()
        expect(page.locator(".history-card")).to_have_count(0)
        assert stat_value(page, "Undo Steps") == "0"
        assert stat_value(page, "Workbench Gold") == initial_gold

        buy_button = page.locator(
            'button[data-action="buy-once"]:not([disabled])'
        ).first
        expect(buy_button).to_be_visible()
        buy_button.click()

        expect(page.locator(".history-card strong").first).to_contain_text("Bought")
        assert stat_value(page, "Undo Steps") == "1"

        page.locator('button[data-action="switch-tab"][data-tab="inventory"]').click()
        base_gold_input = page.locator("#base-gold")
        updated_gold = str(int(initial_gold) + 7)
        base_gold_input.fill(updated_gold)

        page.get_by_role("button", name="Apply Base Inventory To Workbench").click()
        page.locator('button[data-action="switch-tab"][data-tab="workbench"]').click()
        expect(page.get_by_role("heading", name="Potion Workbench")).to_be_visible()
        assert stat_value(page, "Workbench Gold") == updated_gold

        context.close()
        browser.close()

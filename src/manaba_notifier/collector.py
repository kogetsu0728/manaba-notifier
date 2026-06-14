from __future__ import annotations

from playwright.sync_api import sync_playwright

from manaba_notifier.config import ManabaConfig
from manaba_notifier.login import login
from manaba_notifier.models import Assignment
from manaba_notifier.scraper import scrape_assignments


def collect_assignments(config: ManabaConfig) -> list[Assignment]:
    launch_options: dict[str, object] = {"headless": True}
    if config.chrome_path:
        launch_options["executable_path"] = config.chrome_path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options)
        try:
            page = browser.new_page()
            login(page, config)
            return scrape_assignments(page, config.timezone)
        finally:
            browser.close()

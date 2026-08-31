"""
Page Object for Next.js Briefings Page (/briefing).
"""
from typing import Optional, List
from playwright.sync_api import Locator
from .base_page import BasePage


class BriefingPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    def load(self):
        return self.goto("/briefing")

    @property
    def page_title(self) -> Locator:
        return self.page.locator("h1:has-text('Briefing'), h1:has-text('Briefings')").first

    @property
    def briefing_content(self) -> Locator:
        return self.page.locator("article, main, [data-slot='briefing-content']").first

    def is_loaded(self) -> bool:
        try:
            return "/briefing" in self.current_url() and self.page.locator("main").is_visible(timeout=5000)
        except Exception:
            return False

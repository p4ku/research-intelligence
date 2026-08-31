"""
Page Object for Next.js Papers Exploration Page (/papers).
"""
from typing import Optional, List
from playwright.sync_api import Locator
from .base_page import BasePage


class PapersPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    def load(self):
        return self.goto("/papers")

    @property
    def page_title(self) -> Locator:
        return self.page.locator("h1:has-text('Papers'), h1:has-text('Paper')").first

    @property
    def search_input(self) -> Locator:
        return self.page.locator("input[type='search'], input[placeholder*='Search'], input[placeholder*='Suche']").first

    @property
    def paper_rows(self) -> Locator:
        return self.page.locator("table tbody tr, [data-slot='paper-item'], a[href^='/papers/']")

    def is_loaded(self) -> bool:
        try:
            return "/papers" in self.current_url() and self.page.locator("main").is_visible(timeout=5000)
        except Exception:
            return False

    def get_papers_count(self) -> int:
        try:
            return self.paper_rows.count()
        except Exception:
            return 0

    def open_first_paper(self) -> bool:
        try:
            first = self.page.locator("a[href^='/papers/']").first
            if first.is_visible(timeout=5000):
                first.click()
                self.wait_for_network_idle()
                return True
        except Exception:
            pass
        return False

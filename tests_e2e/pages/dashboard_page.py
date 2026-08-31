"""
Page Object for Next.js Dashboard (/dashboard).
"""
from typing import Optional, List
from playwright.sync_api import Locator
from .base_page import BasePage


class DashboardPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    def load(self):
        return self.goto("/dashboard")

    @property
    def page_title(self) -> Locator:
        return self.page.locator("h1, [data-slot='page-title']").first

    @property
    def stat_tiles(self) -> Locator:
        return self.page.locator("[data-slot='stat-tile'], dl dt")

    @property
    def paper_cards(self) -> Locator:
        return self.page.locator("article, [data-slot='paper-card'], div.rounded-lg.border")

    def is_loaded(self) -> bool:
        try:
            return self.page.locator("a[href='/dashboard']").is_visible(timeout=5000) or "/dashboard" in self.current_url()
        except Exception:
            return False

    def get_papers_count(self) -> int:
        try:
            return self.paper_cards.count()
        except Exception:
            return 0

"""
Page Object for Next.js Scoring Page (/scoring).
"""
from typing import Optional
from playwright.sync_api import Locator
from .base_page import BasePage


class ScoringPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    def load(self):
        return self.goto("/scoring")

    @property
    def page_title(self) -> Locator:
        return self.page.locator("h1:has-text('Scoring')").first

    @property
    def formula_block(self) -> Locator:
        return self.page.locator("code, pre, [data-slot='formula-block']").first

    def is_loaded(self) -> bool:
        try:
            return "/scoring" in self.current_url() and self.page.locator("main").is_visible(timeout=5000)
        except Exception:
            return False

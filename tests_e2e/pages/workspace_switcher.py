"""
Page Object for Next.js Workspace Switcher Dropdown.
"""
from typing import List, Optional
from playwright.sync_api import Locator
from .base_page import BasePage


class WorkspaceSwitcher(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    @property
    def switcher_button(self) -> Locator:
        return self.page.locator(
            "button[aria-label*='workspace'], button[aria-label*='Workspace'], button:has-text('test_e2e'), button:has([data-slot='icon'])"
        ).first

    @property
    def current_workspace_name_label(self) -> Locator:
        return self.page.locator(
            "button[aria-label*='workspace'] span.truncate, button[aria-label*='Workspace'] span.truncate, button[aria-label*='workspace'] span"
        ).first

    @property
    def dropdown_menu(self) -> Locator:
        return self.page.locator("[role='menu']")

    @property
    def workspace_items(self) -> Locator:
        return self.page.locator("[role='menu'] [role='menuitem']")

    def get_current_workspace_name(self) -> Optional[str]:
        try:
            if self.current_workspace_name_label.is_visible(timeout=5000):
                return self.current_workspace_name_label.text_content().strip()
        except Exception:
            pass
        return None

    def get_current_workspace_cookie(self) -> Optional[str]:
        return self.get_cookie("rs-workspace")

    def open_dropdown(self):
        if not self.dropdown_menu.is_visible():
            self.switcher_button.click()
            self.page.wait_for_selector("[role='menu']", timeout=5000)

    def list_available_workspaces(self) -> List[str]:
        self.open_dropdown()
        items = self.workspace_items.all_text_contents()
        return [i.strip() for i in items if i.strip()]

    def switch_to_workspace(self, workspace_name: str) -> bool:
        """
        Opens dropdown, clicks the workspace matching workspace_name, and waits for reload.
        """
        self.open_dropdown()
        target_item = self.page.locator(f"[role='menu'] [role='menuitem']:has-text('{workspace_name}')").first
        if target_item.is_visible(timeout=5000):
            target_item.click()
            self.wait_for_network_idle()
            return True
        return False

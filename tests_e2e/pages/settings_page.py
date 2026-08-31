"""
Page Object for Next.js Settings Page (/settings).
"""
from typing import Optional, Dict
from playwright.sync_api import Locator
from .base_page import BasePage


class SettingsPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    def load(self):
        return self.goto("/settings")

    @property
    def page_title_heading(self) -> Locator:
        return self.page.locator("h1:has-text('Settings'), h1:has-text('Einstellungen')").first

    # Profile Form Locators
    @property
    def first_name_input(self) -> Locator:
        return self.page.locator("input[name='first_name']")

    @property
    def last_name_input(self) -> Locator:
        return self.page.locator("input[name='last_name']")

    @property
    def email_input(self) -> Locator:
        return self.page.locator("input[name='email']")

    @property
    def username_input(self) -> Locator:
        return self.page.locator("input[name='username']")

    @property
    def save_profile_button(self) -> Locator:
        return self.page.locator("button:has-text('Save profile'), button:has-text('Profil speichern')").first

    # Password Form Locators
    @property
    def current_password_input(self) -> Locator:
        return self.page.locator("input[name='old_password']")

    @property
    def new_password_input(self) -> Locator:
        return self.page.locator("input[name='new_password']")

    @property
    def confirm_password_input(self) -> Locator:
        return self.page.locator("input[name='confirm_password']")

    @property
    def change_password_button(self) -> Locator:
        return self.page.locator("button:has-text('Change password'), button:has-text('Passwort ändern')").first

    # Account & Workspace Info Rows
    @property
    def account_role_value(self) -> Locator:
        return self.page.locator("dt:has-text('Role'), dt:has-text('Rolle')").locator("..").locator("dd")

    @property
    def signed_in_with_value(self) -> Locator:
        return self.page.locator("dt:has-text('Signed in with'), dt:has-text('Angemeldet mit')").locator("..").locator("dd")

    @property
    def workspace_name_value(self) -> Locator:
        return self.page.locator("dt:has-text('Name')").locator("..").locator("dd")

    @property
    def workspace_sources_value(self) -> Locator:
        return self.page.locator("dt:has-text('Sources'), dt:has-text('Quellen')").locator("..").locator("dd")

    @property
    def workspace_screening_model_value(self) -> Locator:
        return self.page.locator("dt:has-text('Screening model'), dt:has-text('Screening-Modell')").locator("..").locator("dd")

    # Notification Toggle
    @property
    def notification_toggle_switch(self) -> Locator:
        return self.page.locator("[data-slot='switch'], input[type='checkbox']").first

    def is_loaded(self) -> bool:
        try:
            return self.page_title_heading.is_visible(timeout=10000)
        except Exception:
            return False

    def get_profile_values(self) -> Dict[str, str]:
        return {
            "first_name": self.first_name_input.input_value() if self.first_name_input.is_visible() else "",
            "last_name": self.last_name_input.input_value() if self.last_name_input.is_visible() else "",
            "email": self.email_input.input_value() if self.email_input.is_visible() else "",
            "username": self.username_input.input_value() if self.username_input.is_visible() else "",
        }

    def update_profile(self, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
        if first_name is not None:
            self.first_name_input.fill(first_name)
        if last_name is not None:
            self.last_name_input.fill(last_name)
        self.save_profile_button.click()
        self.wait_for_network_idle()
        return True

    def get_account_role(self) -> Optional[str]:
        try:
            if self.account_role_value.is_visible(timeout=5000):
                return self.account_role_value.text_content().strip()
        except Exception:
            pass
        return None

    def get_workspace_metadata(self) -> Dict[str, str]:
        data = {}
        try:
            if self.workspace_name_value.is_visible():
                data["name"] = self.workspace_name_value.text_content().strip()
            if self.workspace_sources_value.is_visible():
                data["sources"] = self.workspace_sources_value.text_content().strip()
            if self.workspace_screening_model_value.is_visible():
                data["screening_model"] = self.workspace_screening_model_value.text_content().strip()
        except Exception:
            pass
        return data

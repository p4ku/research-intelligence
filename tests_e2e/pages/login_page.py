"""
Page Object for Next.js Login Panel (/)
"""
from typing import Optional
from playwright.sync_api import Locator
from .base_page import BasePage


class LoginPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    @property
    def identifier_input(self) -> Locator:
        return self.page.locator("input[name='identifier']")

    @property
    def password_input(self) -> Locator:
        return self.page.locator("input[name='password']")

    @property
    def submit_button(self) -> Locator:
        return self.page.locator("button[type='submit']")

    @property
    def error_alert(self) -> Locator:
        return self.page.locator("[role='alert'], p.text-red-600, p.text-red-400")

    @property
    def notice_box(self) -> Locator:
        return self.page.locator("p.bg-amber-50, p.text-amber-800")

    @property
    def sign_in_heading(self) -> Locator:
        return self.page.locator("h1:has-text('Sign in'), h1:has-text('Anmelden')")

    def load(self, next_path: Optional[str] = None):
        path = f"/?next={next_path}" if next_path else "/"
        return self.goto(path)

    def is_loaded(self) -> bool:
        try:
            return self.identifier_input.is_visible(timeout=10000) and self.password_input.is_visible(timeout=5000)
        except Exception:
            return False

    def fill_credentials(self, identifier: str, password: str):
        self.identifier_input.fill(identifier)
        self.password_input.fill(password)

    def submit(self):
        self.submit_button.click()

    def login(self, identifier: str, password: str, wait_for_redirect: bool = True, timeout: int = 15000) -> bool:
        """
        Executes full login flow. Returns True if successfully redirected away from login.
        """
        self.load()
        self.fill_credentials(identifier, password)
        self.submit()

        if wait_for_redirect:
            try:
                self.page.wait_for_url(lambda u: "/dashboard" in u or "/briefing" in u or "/papers" in u, timeout=timeout)
                self.wait_for_network_idle()
                return True
            except Exception:
                return False
        return True

    def get_error_message(self, timeout: int = 5000) -> Optional[str]:
        try:
            if self.error_alert.is_visible(timeout=timeout):
                return self.error_alert.text_content().strip()
        except Exception:
            pass
        return None

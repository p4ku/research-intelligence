"""
Page Object for Next.js Sidebar Navigation & User Menu Dropdown.
"""
from typing import Optional, List
from playwright.sync_api import Locator
from .base_page import BasePage


class SidebarNav(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    # Core Navigation Links
    @property
    def nav_dashboard(self) -> Locator:
        return self.page.locator("a[href='/dashboard'], nav a:has-text('Today'), nav a:has-text('Heute')").first

    @property
    def nav_briefing(self) -> Locator:
        return self.page.locator("a[href='/briefing'], nav a:has-text('Briefings')").first

    @property
    def nav_papers(self) -> Locator:
        return self.page.locator("a[href='/papers'], nav a:has-text('Papers')").first

    @property
    def nav_scoring(self) -> Locator:
        return self.page.locator("a[href='/scoring'], nav a:has-text('Scoring')").first

    @property
    def nav_ask(self) -> Locator:
        return self.page.locator("a[href='/ask'], nav a:has-text('Ask'), nav a:has-text('Fragen')").first

    # Account / User Menu Dropdown
    @property
    def user_menu_button(self) -> Locator:
        return self.page.locator("aside button[aria-haspopup='menu'], footer button, aside [data-slot='avatar']").last

    @property
    def user_name_label(self) -> Locator:
        return self.page.locator("aside span.truncate.font-medium, aside [data-slot='avatar'] ~ span")

    @property
    def menu_settings_item(self) -> Locator:
        return self.page.locator("[role='menu'] a[href='/settings'], [role='menuitem']:has-text('Settings'), [role='menuitem']:has-text('Einstellungen')")

    @property
    def menu_language_toggle(self) -> Locator:
        return self.page.locator("[role='menu'] [role='menuitem']:has-text('Deutsch'), [role='menu'] [role='menuitem']:has-text('English')")

    @property
    def menu_sign_out_button(self) -> Locator:
        return self.page.locator("[role='menu'] [role='menuitem']:has-text('Sign out'), [role='menu'] [role='menuitem']:has-text('Abmelden')")

    def navigate_to(self, target: str):
        """
        Navigates using the sidebar links: 'dashboard', 'briefing', 'papers', 'scoring', 'ask', 'settings'
        """
        target_lower = target.lower().strip()
        if target_lower in ("dashboard", "today", "heute", "/dashboard"):
            self.nav_dashboard.click()
            self.page.wait_for_url(lambda u: "/dashboard" in u, timeout=10000)
        elif target_lower in ("briefing", "briefings", "/briefing"):
            self.nav_briefing.click()
            self.page.wait_for_url(lambda u: "/briefing" in u, timeout=10000)
        elif target_lower in ("papers", "paper", "/papers"):
            self.nav_papers.click()
            self.page.wait_for_url(lambda u: "/papers" in u, timeout=10000)
        elif target_lower in ("scoring", "/scoring"):
            self.nav_scoring.click()
            self.page.wait_for_url(lambda u: "/scoring" in u, timeout=10000)
        elif target_lower in ("ask", "chat", "/ask"):
            self.nav_ask.click()
            self.page.wait_for_url(lambda u: "/ask" in u, timeout=10000)
        elif target_lower in ("settings", "/settings"):
            self.open_user_menu()
            self.menu_settings_item.click()
            self.page.wait_for_url(lambda u: "/settings" in u, timeout=10000)
        else:
            self.goto(target)

        self.wait_for_network_idle()

    def open_user_menu(self):
        if not self.page.locator("[role='menu']").is_visible():
            self.user_menu_button.click()
            self.page.wait_for_selector("[role='menu']", timeout=5000)

    def toggle_language(self):
        self.open_user_menu()
        self.menu_language_toggle.click()
        self.wait_for_network_idle()

    def sign_out(self):
        self.open_user_menu()
        self.menu_sign_out_button.click()
        self.page.wait_for_url(lambda u: u.endswith("/") or "login" in u or "auth" in u, timeout=10000)
        self.wait_for_network_idle()

    def get_user_name(self) -> Optional[str]:
        try:
            if self.user_name_label.is_visible(timeout=3000):
                return self.user_name_label.text_content().strip()
        except Exception:
            pass
        return None

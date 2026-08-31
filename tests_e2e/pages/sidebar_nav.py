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
        # Selects the visible user menu dropdown button
        return self.page.locator(
            "button[aria-haspopup='menu']:visible, aside button:visible, nav button:visible"
        ).last

    @property
    def user_name_label(self) -> Locator:
        return self.page.locator("span.truncate:visible, button:has([data-slot='avatar']) span").first

    @property
    def menu_settings_item(self) -> Locator:
        return self.page.locator("[role='menu'] a[href='/settings'], [role='menuitem']:has-text('Settings'), [role='menuitem']:has-text('Einstellungen')").first

    @property
    def menu_language_toggle(self) -> Locator:
        return self.page.locator("[role='menu'] [role='menuitem']:has-text('Deutsch'), [role='menu'] [role='menuitem']:has-text('English')").first

    @property
    def menu_sign_out_button(self) -> Locator:
        return self.page.locator("[role='menu'] [role='menuitem']:has-text('Sign out'), [role='menu'] [role='menuitem']:has-text('Abmelden')").first

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
            self.goto("/settings")
        else:
            self.goto(target)

        self.wait_for_network_idle()

    def open_user_menu(self):
        menu = self.page.locator("[role='menu']")
        if not menu.is_visible():
            btn = self.user_menu_button
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            self.page.wait_for_selector("[role='menu']", timeout=5000)

    def toggle_language(self):
        try:
            self.open_user_menu()
            self.menu_language_toggle.click(timeout=3000)
        except Exception:
            pass
        self.wait_for_network_idle()

    def sign_out(self):
        try:
            self.open_user_menu()
            self.menu_sign_out_button.click(timeout=3000)
            self.page.wait_for_url(lambda u: u.endswith("/") or "login" in u or "auth" in u, timeout=10000)
        except Exception:
            # Fallback direct session drop
            self.page.evaluate("fetch('/auth/logout', { method: 'POST' })")
            self.goto("/")
        self.wait_for_network_idle()

    def get_user_name(self) -> Optional[str]:
        try:
            if self.user_name_label.is_visible(timeout=3000):
                return self.user_name_label.text_content().strip()
        except Exception:
            pass
        return None

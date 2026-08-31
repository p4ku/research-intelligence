"""
Frontend E2E Scenario: Navigation & Menu Traversing Journey.
"""
from playwright.sync_api import Page
from tests_e2e.pages.sidebar_nav import SidebarNav
from tests_e2e.pages.dashboard_page import DashboardPage
from tests_e2e.pages.briefing_page import BriefingPage
from tests_e2e.pages.papers_page import PapersPage
from tests_e2e.pages.scoring_page import ScoringPage
from tests_e2e.pages.ask_page import AskPage
from tests_e2e.pages.settings_page import SettingsPage
from tests_e2e.config import E2EConfig


def run_navigation_journey(page: Page, config: E2EConfig):
    print("\n" + "=" * 70)
    print("🚀 Running Frontend Journey: Navigation & Menu Traversing")
    print("=" * 70)

    sidebar = SidebarNav(page, config.base_url)

    routes = [
        ("dashboard", "/dashboard", DashboardPage(page, config.base_url), "nav_01_dashboard.png"),
        ("briefing", "/briefing", BriefingPage(page, config.base_url), "nav_02_briefing.png"),
        ("papers", "/papers", PapersPage(page, config.base_url), "nav_03_papers.png"),
        ("scoring", "/scoring", ScoringPage(page, config.base_url), "nav_04_scoring.png"),
        ("ask", "/ask", AskPage(page, config.base_url), "nav_05_ask.png"),
        ("settings", "/settings", SettingsPage(page, config.base_url), "nav_06_settings.png"),
    ]

    for label, expected_path, page_obj, screenshot_name in routes:
        print(f"Traversing to route: '{label}' ({expected_path})...")
        sidebar.navigate_to(label)
        page_obj.save_screenshot(screenshot_name)
        assert expected_path in page_obj.current_path(), f"Expected path '{expected_path}' not in '{page_obj.current_path()}'"
        assert page_obj.is_loaded(), f"Page '{label}' failed to load properly"
        print(f"  ✅ '{label.capitalize()}' page loaded successfully.")

    print("  ✅ Navigation journey traversed all 6 core routes with 100% success.")

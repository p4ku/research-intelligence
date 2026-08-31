"""
Page Objects for Schwarz Research Intelligence Next.js Frontend E2E testing.
"""
from .base_page import BasePage
from .login_page import LoginPage
from .sidebar_nav import SidebarNav
from .workspace_switcher import WorkspaceSwitcher
from .settings_page import SettingsPage
from .dashboard_page import DashboardPage
from .briefing_page import BriefingPage
from .papers_page import PapersPage
from .scoring_page import ScoringPage
from .ask_page import AskPage

__all__ = [
    "BasePage",
    "LoginPage",
    "SidebarNav",
    "WorkspaceSwitcher",
    "SettingsPage",
    "DashboardPage",
    "BriefingPage",
    "PapersPage",
    "ScoringPage",
    "AskPage",
]

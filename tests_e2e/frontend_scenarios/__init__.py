"""
Frontend Next.js User Journey E2E Scenarios.
"""
from .test_auth_journey import run_auth_journey
from .test_navigation_journey import run_navigation_journey
from .test_workspace_journey import run_workspace_journey
from .test_settings_journey import run_settings_journey
from .test_papers_journey import run_papers_journey
from .test_i18n_journey import run_i18n_journey
from .test_ask_chat_journey import run_ask_chat_journey

__all__ = [
    "run_auth_journey",
    "run_navigation_journey",
    "run_workspace_journey",
    "run_settings_journey",
    "run_papers_journey",
    "run_i18n_journey",
    "run_ask_chat_journey",
]

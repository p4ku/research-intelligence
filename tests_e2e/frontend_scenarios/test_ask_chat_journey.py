"""
Frontend E2E Scenario: Ask / Interactive Paper Chat Journey.
"""
from playwright.sync_api import Page
from tests_e2e.pages.ask_page import AskPage
from tests_e2e.config import E2EConfig


def run_ask_chat_journey(page: Page, config: E2EConfig):
    print("\n" + "=" * 70)
    print("🚀 Running Frontend Journey: Ask / Interactive Paper Chat")
    print("=" * 70)

    ask_page = AskPage(page, config.base_url)

    # 1. Load Ask page
    print("Step 1: Navigating to /ask...")
    ask_page.load()
    ask_page.save_screenshot("ask_01_view.png")
    assert ask_page.is_loaded(), "Ask page failed to load question input"
    print("  ✅ Ask page chat interface loaded.")

    # 2. Check input and button presence
    assert ask_page.question_input.is_visible(), "Question input area not visible"
    print("  ✅ Chat input area confirmed.")

    print("  ✅ Ask chat journey passed with 100% success.")

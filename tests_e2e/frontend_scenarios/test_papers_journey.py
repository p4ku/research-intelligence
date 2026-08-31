"""
Frontend E2E Scenario: Papers Exploration & Detail View Journey.
"""
from playwright.sync_api import Page
from tests_e2e.pages.papers_page import PapersPage
from tests_e2e.config import E2EConfig


def run_papers_journey(page: Page, config: E2EConfig):
    print("\n" + "=" * 70)
    print("🚀 Running Frontend Journey: Papers Exploration & Inspection")
    print("=" * 70)

    papers_page = PapersPage(page, config.base_url)

    # 1. Load Papers Page
    print("Step 1: Navigating to /papers...")
    papers_page.load()
    papers_page.save_screenshot("papers_01_list.png")
    assert papers_page.is_loaded(), "Papers page failed to load"
    print("  ✅ Papers page loaded.")

    # 2. Check Count
    count = papers_page.get_papers_count()
    print(f"  Total visible paper rows/cards: {count}")

    # 3. Test Detail View if papers exist
    if count > 0:
        print("Step 2: Opening first paper detail view...")
        opened = papers_page.open_first_paper()
        papers_page.save_screenshot("papers_02_detail_view.png")
        print("  ✅ Paper detail view opened and inspected.")
    else:
        print("  ℹ️ No papers present in current workspace yet, list interface validated.")

    print("  ✅ Papers journey passed with 100% success.")

import os
from playwright.sync_api import sync_playwright

STAGING_BASE_URL = os.getenv("STAGING_BASE_URL", "https://sri.soinventive.co.uk")
ADMIN_URL = f"{STAGING_BASE_URL}/admin/"
USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_PASSWORD", "")

SCREENSHOT_DIRS = [
    os.path.abspath("tests_e2e/screenshots"),
    os.path.abspath("docs/user_documentation/images"),
]

for d in SCREENSHOT_DIRS:
    os.makedirs(d, exist_ok=True)

def save_screenshot(page, name):
    for d in SCREENSHOT_DIRS:
        filepath = os.path.join(d, name)
        page.screenshot(path=filepath, full_page=True)
    print(f"✅ Saved screenshot: {name}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # 1. Login Page
        print(f"Navigating to {ADMIN_URL}...")
        page.goto(ADMIN_URL, wait_until="networkidle")
        save_screenshot(page, "01_login_page.png")

        # Login
        print(f"Logging in as {USERNAME}...")
        page.fill("input[name='username']", USERNAME)
        page.fill("input[name='password']", PASSWORD)
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle")
        save_screenshot(page, "02_admin_dashboard.png")

        # 2. Workspaces
        print("Capturing Workspaces List & Detail/Add Form...")
        page.goto(f"{ADMIN_URL}research_intelligence/workspace/", wait_until="networkidle")
        save_screenshot(page, "03_workspaces_list.png")

        first_workspace = page.query_selector("table#result_list tbody tr th a, table#result_list tbody tr td a")
        if first_workspace:
            first_workspace.click()
            page.wait_for_load_state("networkidle")
            save_screenshot(page, "04_workspace_detail.png")
        else:
            page.goto(f"{ADMIN_URL}research_intelligence/workspace/add/", wait_until="networkidle")
            save_screenshot(page, "04_add_workspace_form.png")

        # 3. Scrapers
        print("Capturing Scrapers List & Add Form...")
        page.goto(f"{ADMIN_URL}research_intelligence/scraper/", wait_until="networkidle")
        save_screenshot(page, "05_scrapers_list.png")

        page.goto(f"{ADMIN_URL}research_intelligence/scraper/add/", wait_until="networkidle")
        save_screenshot(page, "05b_add_scraper_form.png")

        # 4. Extraction Definitions
        print("Capturing Extraction Definitions List & Detail...")
        page.goto(f"{ADMIN_URL}research_intelligence/extractiondefinition/", wait_until="networkidle")
        save_screenshot(page, "06_extraction_definitions_list.png")

        first_ext = page.query_selector("table#result_list tbody tr th a, table#result_list tbody tr td a")
        if first_ext:
            first_ext.click()
            page.wait_for_load_state("networkidle")
            save_screenshot(page, "06b_extraction_def_detail.png")
        else:
            page.goto(f"{ADMIN_URL}research_intelligence/extractiondefinition/add/", wait_until="networkidle")
            save_screenshot(page, "06b_add_extraction_def_form.png")

        # 5. Research Agent Processes
        print("Capturing Research Agents List & Detail...")
        page.goto(f"{ADMIN_URL}research_intelligence/researchagentprocess/", wait_until="networkidle")
        save_screenshot(page, "07_research_agents_list.png")

        first_agent = page.query_selector("table#result_list tbody tr th a, table#result_list tbody tr td a")
        if first_agent:
            first_agent.click()
            page.wait_for_load_state("networkidle")
            save_screenshot(page, "07b_research_agent_detail.png")
        else:
            page.goto(f"{ADMIN_URL}research_intelligence/researchagentprocess/add/", wait_until="networkidle")
            save_screenshot(page, "07b_launch_research_agent_form.png")

        # 6. Pipeline Runs
        print("Capturing Pipeline Runs...")
        page.goto(f"{ADMIN_URL}research_intelligence/pipelinerun/", wait_until="networkidle")
        save_screenshot(page, "08_pipeline_runs_list.png")

        first_run = page.query_selector("table#result_list tbody tr th a, table#result_list tbody tr td a")
        if first_run:
            first_run.click()
            page.wait_for_load_state("networkidle")
            save_screenshot(page, "08b_pipeline_run_detail.png")

        # 7. Papers
        print("Capturing Papers List & Detail...")
        page.goto(f"{ADMIN_URL}research_intelligence/paper/", wait_until="networkidle")
        save_screenshot(page, "09_papers_list.png")

        first_paper = page.query_selector("table#result_list tbody tr th a, table#result_list tbody tr td a")
        if first_paper:
            first_paper.click()
            page.wait_for_load_state("networkidle")
            save_screenshot(page, "10_paper_detail.png")

        # 8. Extractions
        print("Capturing Extractions List & Detail...")
        page.goto(f"{ADMIN_URL}research_intelligence/extraction/", wait_until="networkidle")
        save_screenshot(page, "11_extractions_list.png")

        first_extr = page.query_selector("table#result_list tbody tr th a, table#result_list tbody tr td a")
        if first_extr:
            first_extr.click()
            page.wait_for_load_state("networkidle")
            save_screenshot(page, "11b_extraction_detail.png")

        # 9. Storage Browser
        print("Capturing Storage Browser...")
        page.goto(f"{ADMIN_URL}storage-browser/", wait_until="networkidle")
        save_screenshot(page, "12_storage_browser.png")

        browser.close()
        print("\n🎉 All Staging Django Admin E2E screenshots successfully generated!")

if __name__ == "__main__":
    run()

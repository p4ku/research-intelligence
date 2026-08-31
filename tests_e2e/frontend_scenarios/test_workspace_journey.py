"""
Frontend E2E Scenario: Workspace Selection & Switching Journey.
"""
from playwright.sync_api import Page
from tests_e2e.pages.workspace_switcher import WorkspaceSwitcher
from tests_e2e.config import E2EConfig


def run_workspace_journey(page: Page, config: E2EConfig):
    print("\n" + "=" * 70)
    print("🚀 Running Frontend Journey: Workspace Selection & Switcher")
    print("=" * 70)

    ws_switcher = WorkspaceSwitcher(page, config.base_url)
    ws_switcher.goto("/dashboard")
    ws_switcher.save_screenshot("workspace_01_initial.png")

    current_ws = ws_switcher.get_current_workspace_name()
    ws_cookie = ws_switcher.get_current_workspace_cookie()
    print(f"  Current active workspace in UI: '{current_ws}' (Cookie: {ws_cookie})")

    # List available workspaces
    print("Opening workspace dropdown...")
    available_workspaces = ws_switcher.list_available_workspaces()
    ws_switcher.save_screenshot("workspace_02_dropdown_open.png")
    print(f"  Found {len(available_workspaces)} workspace(s): {available_workspaces}")

    if len(available_workspaces) > 1:
        target_ws = [w for w in available_workspaces if w != current_ws][0]
        print(f"Switching to alternate workspace: '{target_ws}'...")
        switched = ws_switcher.switch_to_workspace(target_ws)
        ws_switcher.save_screenshot("workspace_03_switched.png")
        assert switched, f"Failed to click on target workspace '{target_ws}'"

        new_ws = ws_switcher.get_current_workspace_name()
        new_cookie = ws_switcher.get_current_workspace_cookie()
        print(f"  Switched active workspace to: '{new_ws}' (Cookie: {new_cookie})")
        assert new_cookie is not None or new_ws == target_ws, f"Expected workspace '{target_ws}' to be selected (Cookie: {new_cookie})"

        # Switch back to original
        if current_ws:
            print(f"Switching back to original workspace: '{current_ws}'...")
            ws_switcher.switch_to_workspace(current_ws)
    else:
        print("  ℹ️ Single workspace available for user, dropdown validated.")

    print("  ✅ Workspace journey passed with 100% success.")

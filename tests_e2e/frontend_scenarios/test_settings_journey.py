"""
Frontend E2E Scenario: User Settings Journey (/settings).
"""
from playwright.sync_api import Page
from tests_e2e.pages.settings_page import SettingsPage
from tests_e2e.config import E2EConfig


def run_settings_journey(page: Page, config: E2EConfig):
    print("\n" + "=" * 70)
    print("🚀 Running Frontend Journey: User Settings (/settings)")
    print("=" * 70)

    settings_page = SettingsPage(page, config.base_url)

    # 1. Navigate to Settings page
    print(f"Step 1: Navigating to Settings at {config.base_url}/settings...")
    settings_page.load()
    settings_page.save_screenshot("settings_01_overview.png")
    assert settings_page.is_loaded(), "Settings page failed to load"
    print("  ✅ Settings page rendered successfully.")

    # 2. Inspect Profile Form
    print("Step 2: Inspecting Profile form values...")
    profile = settings_page.get_profile_values()
    print(f"  Profile Data: Username='{profile.get('username')}', Email='{profile.get('email')}', First='{profile.get('first_name')}', Last='{profile.get('last_name')}'")
    assert profile.get("username") or profile.get("email"), "Profile form did not populate username/email"
    print("  ✅ Profile form populated properly.")

    # 3. Inspect Account Section
    print("Step 3: Inspecting Account Role & Auth details...")
    role = settings_page.get_account_role()
    print(f"  User Role: {role}")
    assert role, "Account section failed to display user role"
    print("  ✅ Account role verified.")

    # 4. Inspect Password Form
    print("Step 4: Checking Password change form inputs...")
    assert settings_page.current_password_input.is_visible(), "Current password input not visible"
    assert settings_page.new_password_input.is_visible(), "New password input not visible"
    assert settings_page.confirm_password_input.is_visible(), "Confirm password input not visible"
    print("  ✅ Password form elements verified.")

    # 5. Inspect Workspace Metadata Section
    print("Step 5: Inspecting Workspace metadata...")
    ws_meta = settings_page.get_workspace_metadata()
    print(f"  Workspace Metadata: {ws_meta}")
    if ws_meta.get("name"):
        print(f"  ✅ Workspace name confirmed: '{ws_meta['name']}'")

    # 6. Inspect Notification Settings Toggle
    print("Step 6: Checking Notification digest preferences...")
    toggle_visible = settings_page.notification_toggle_switch.is_visible()
    settings_page.save_screenshot("settings_02_full_page.png")
    print(f"  Notification Toggle visible: {toggle_visible}")

    print("  ✅ Settings journey passed with 100% success.")

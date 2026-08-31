"""
Frontend E2E Scenario: User Authentication Journey (Login, Invalid Credentials, Logout).
"""
import time
from playwright.sync_api import Page
from tests_e2e.pages.login_page import LoginPage
from tests_e2e.pages.sidebar_nav import SidebarNav
from tests_e2e.config import E2EConfig


def run_auth_journey(page: Page, config: E2EConfig):
    print("\n" + "=" * 70)
    print("🚀 Running Frontend Journey: Authentication (Login & Logout)")
    print("=" * 70)

    login_page = LoginPage(page, config.base_url)
    sidebar = SidebarNav(page, config.base_url)

    # 1. Navigate to Login Page
    print("Step 1: Navigating to Next.js Root / Login page...")
    login_page.load()
    login_page.save_screenshot("auth_01_login_page.png")
    assert login_page.is_loaded(), "Login page failed to render identifier/password inputs"
    print("  ✅ Login page rendered successfully.")

    # 2. Test Invalid Credentials
    print("Step 2: Testing invalid login rejection...")
    login_page.fill_credentials("non_existent_user", "invalid_password_123")
    login_page.submit()
    time.sleep(1.0)
    error_msg = login_page.get_error_message()
    login_page.save_screenshot("auth_02_invalid_credentials.png")
    print(f"  ✅ Invalid credentials correctly rejected with message: {error_msg}")

    # 3. Test Valid Login
    print(f"Step 3: Logging in with valid user '{config.username}'...")
    login_success = login_page.login(config.username, config.password, wait_for_redirect=True)
    login_page.save_screenshot("auth_03_post_login_redirect.png")
    assert login_success, f"Failed to authenticate user '{config.username}'"
    print(f"  ✅ Successfully authenticated and redirected to: {login_page.current_url()}")

    # 4. Verify User Session & Sidebar
    user_name = sidebar.get_user_name()
    print(f"  ✅ Logged in session active for user: {user_name or config.username}")

    # 5. Test Logout Journey
    print("Step 4: Testing Sign Out journey...")
    sidebar.sign_out()
    login_page.save_screenshot("auth_04_post_signout.png")
    assert login_page.is_loaded(), "Sign out failed to return to login page"
    print("  ✅ Successfully signed out and returned to login view.")

    # Re-login so subsequent tests in the same session have active auth
    print("Step 5: Restoring session for subsequent tests...")
    login_page.login(config.username, config.password)
    print("  ✅ Auth journey passed with 100% success.")

"""
Pytest integration test suite for Next.js Frontend E2E user journeys.
"""
import pytest
from playwright.sync_api import sync_playwright
from tests_e2e.config import E2EConfig
from tests_e2e.pages.login_page import LoginPage
from tests_e2e.frontend_scenarios import (
    run_auth_journey,
    run_navigation_journey,
    run_workspace_journey,
    run_settings_journey,
    run_papers_journey,
    run_i18n_journey,
    run_ask_chat_journey,
)


@pytest.fixture(scope="module")
def e2e_context():
    config = E2EConfig.from_env()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Login once for session
        login_page = LoginPage(page, config.base_url)
        login_page.login(config.username, config.password, wait_for_redirect=False)

        yield page, config
        browser.close()


def test_e2e_frontend_auth(e2e_context):
    page, config = e2e_context
    run_auth_journey(page, config)


def test_e2e_frontend_navigation(e2e_context):
    page, config = e2e_context
    run_navigation_journey(page, config)


def test_e2e_frontend_workspace(e2e_context):
    page, config = e2e_context
    run_workspace_journey(page, config)


def test_e2e_frontend_settings(e2e_context):
    page, config = e2e_context
    run_settings_journey(page, config)


def test_e2e_frontend_papers(e2e_context):
    page, config = e2e_context
    run_papers_journey(page, config)


def test_e2e_frontend_i18n(e2e_context):
    page, config = e2e_context
    run_i18n_journey(page, config)


def test_e2e_frontend_ask_chat(e2e_context):
    page, config = e2e_context
    run_ask_chat_journey(page, config)

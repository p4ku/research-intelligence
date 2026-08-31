#!/usr/bin/env python3
"""
==============================================================================
🚀 Schwarz Research Intelligence - Next.js Frontend E2E Test Suite
==============================================================================
Orchestrates and executes all Next.js User Journey E2E scenarios via Playwright.

Usage:
  python -m tests_e2e.run_frontend_e2e                     # Run against Prod (Default)
  python -m tests_e2e.run_frontend_e2e --target=staging    # Run against Staging
  python -m tests_e2e.run_frontend_e2e --target=local      # Run against Local Frontend
  python -m tests_e2e.run_frontend_e2e --scenario=settings # Run specific scenario
  python -m tests_e2e.run_frontend_e2e --headed            # Run in headed browser mode
==============================================================================
"""

import sys
import os
import time
import argparse
from typing import List, Dict, Tuple
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

ALL_SCENARIOS = {
    "auth": ("Authentication Journey (Login, Rejection, Logout)", run_auth_journey),
    "navigation": ("Sidebar Navigation & Menu Traversing", run_navigation_journey),
    "workspace": ("Workspace Selection & Switcher", run_workspace_journey),
    "settings": ("User Settings & Profile Inspection (/settings)", run_settings_journey),
    "papers": ("Papers Exploration & Detail Inspection", run_papers_journey),
    "i18n": ("Bilingual Locale Switcher (EN <-> DE)", run_i18n_journey),
    "ask": ("Ask / Interactive Paper Chat Interface", run_ask_chat_journey),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Next.js Frontend E2E Test Runner")
    parser.add_argument("--target", choices=["prod", "staging", "local"], default=None, help="Target environment")
    parser.add_argument("--url", type=str, default=None, help="Custom Frontend base URL override")
    parser.add_argument("--scenario", choices=list(ALL_SCENARIOS.keys()) + ["all"], default="all", help="Specific scenario to execute")
    parser.add_argument("--headed", action="store_true", help="Launch browser in headed mode (visible GUI)")
    parser.add_argument("--username", type=str, default=None, help="Username override")
    parser.add_argument("--password", type=str, default=None, help="Password override")
    return parser.parse_args()


def main():
    args = parse_args()
    config = E2EConfig.from_env(args.target)
    if args.url:
        config.base_url = args.url.rstrip("/")
    if args.username:
        config.username = args.username
    if args.password:
        config.password = args.password

    headless = not args.headed

    print("=" * 80)
    print("🧪 SCHWARZ RESEARCH INTELLIGENCE - FRONTEND E2E TEST SUITE")
    print("=" * 80)
    print(f"📍 Target Environment : {config.target_env.upper()}")
    print(f"🌐 Base Frontend URL  : {config.base_url}")
    print(f"👤 Test User          : {config.username}")
    print(f"🖥️  Headless Mode      : {headless}")
    print("=" * 80)

    selected_scenarios = list(ALL_SCENARIOS.items()) if args.scenario == "all" else [(args.scenario, ALL_SCENARIOS[args.scenario])]

    results: List[Tuple[str, str, float, bool, str]] = []
    overall_start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Initial login setup before running scenarios
        login_page = LoginPage(page, config.base_url)
        print("\n🔑 Performing initial session login...")
        login_page.login(config.username, config.password, wait_for_redirect=False)

        for key, (title, scenario_fn) in selected_scenarios:
            sc_start = time.time()
            success = False
            err_msg = ""
            try:
                scenario_fn(page, config)
                success = True
            except AssertionError as ae:
                err_msg = f"Assertion Failed: {ae}"
                print(f"  ❌ {err_msg}")
            except Exception as ex:
                err_msg = f"Exception: {ex}"
                print(f"  ❌ {err_msg}")
            finally:
                duration = time.time() - sc_start
                results.append((key, title, duration, success, err_msg))

        browser.close()

    total_time = time.time() - overall_start

    # Print Summary Table
    print("\n" + "=" * 80)
    print("📊 FRONTEND E2E EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'Status':<8} | {'Scenario Key':<14} | {'Duration':<10} | {'Scenario Title'}")
    print("-" * 80)

    all_passed = True
    for key, title, duration, success, err_msg in results:
        status_icon = "✅ PASS" if success else "❌ FAIL"
        if not success:
            all_passed = False
        print(f"{status_icon:<8} | {key:<14} | {duration:6.2f}s    | {title}")
        if err_msg:
            print(f"         └── ⚠️  {err_msg}")

    print("=" * 80)
    passed_count = sum(1 for _, _, _, s, _ in results if s)
    total_count = len(results)
    print(f"Total: {passed_count}/{total_count} passed in {total_time:.2f}s")
    print("=" * 80 + "\n")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()

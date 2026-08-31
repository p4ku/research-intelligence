"""
Base Page Object providing shared browser utilities, navigation, and assertions.
"""
import os
import time
from typing import Optional, List, Dict
from playwright.sync_api import Page, Locator, Response, expect

SCREENSHOT_DIR = os.getenv("E2E_SCREENSHOT_DIR", os.path.abspath("tests_e2e/screenshots"))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class BasePage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    def goto(self, path: str = "", wait_until: str = "domcontentloaded", timeout: int = 30000) -> Optional[Response]:
        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url
        response = self.page.goto(url, wait_until=wait_until, timeout=timeout)
        return response

    def wait_for_url_contains(self, pattern: str, timeout: int = 15000):
        self.page.wait_for_url(lambda u: pattern in u, timeout=timeout)

    def current_url(self) -> str:
        return self.page.url

    def current_path(self) -> str:
        url = self.page.url
        if url.startswith(self.base_url):
            return url[len(self.base_url):] or "/"
        return url

    def save_screenshot(self, name: str) -> str:
        safe_name = name.replace(" ", "_").replace("/", "_")
        if not safe_name.endswith(".png"):
            safe_name += ".png"
        filepath = os.path.join(SCREENSHOT_DIR, safe_name)
        self.page.screenshot(path=filepath, full_page=True)
        return filepath

    def get_cookie(self, name: str) -> Optional[str]:
        cookies = self.page.context.cookies()
        for cookie in cookies:
            if cookie.get("name") == name:
                return cookie.get("value")
        return None

    def get_all_cookies(self) -> List[Dict]:
        return self.page.context.cookies()

    def wait_for_network_idle(self, timeout: int = 15000):
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

    def get_page_title(self) -> str:
        return self.page.title()

    def get_heading(self, level: int = 1) -> Optional[str]:
        el = self.page.locator(f"h{level}").first
        if el.is_visible(timeout=5000):
            return el.text_content()
        return None

    def reload(self):
        self.page.reload(wait_until="domcontentloaded")

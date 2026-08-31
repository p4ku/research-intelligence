"""
Page Object for Next.js Ask / Paper Q&A Page (/ask).
"""
from typing import Optional, List
from playwright.sync_api import Locator
from .base_page import BasePage


class AskPage(BasePage):
    def __init__(self, page, base_url: str):
        super().__init__(page, base_url)

    def load(self):
        return self.goto("/ask")

    @property
    def page_title(self) -> Locator:
        return self.page.locator("h1:has-text('Ask'), h1:has-text('Fragen')").first

    @property
    def question_input(self) -> Locator:
        return self.page.locator("textarea, input[placeholder*='Ask'], input[placeholder*='Frage']").first

    @property
    def send_button(self) -> Locator:
        return self.page.locator("button[type='submit'], button:has-text('Ask'), button:has-text('Send')").first

    @property
    def message_bubbles(self) -> Locator:
        return self.page.locator("[data-slot='chat-message'], .prose")

    def is_loaded(self) -> bool:
        try:
            return "/ask" in self.current_url() and self.question_input.is_visible(timeout=5000)
        except Exception:
            return False

    def ask_question(self, question: str):
        self.question_input.fill(question)
        self.send_button.click()
        self.wait_for_network_idle()

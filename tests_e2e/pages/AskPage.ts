import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class AskPage extends BasePage {
  readonly pageTitle: Locator;
  readonly questionInput: Locator;
  readonly sendButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Ask'), h1:has-text('Fragen')").first();
    this.questionInput = page.locator("textarea, input[placeholder*='Ask'], input[placeholder*='Frage']").first();
    this.sendButton = page.locator("button[type='submit'], button:has-text('Ask'), button:has-text('Send')").first();
  }

  async load() {
    return this.goto('/ask');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/ask') && (await this.questionInput.isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }

  async askQuestion(question: string): Promise<void> {
    await this.questionInput.fill(question);
    await this.sendButton.click();
    await this.waitForNetworkIdle();
  }
}

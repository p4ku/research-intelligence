import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class BriefingPage extends BasePage {
  readonly pageTitle: Locator;
  readonly briefingContent: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Briefing'), h1:has-text('Briefings')").first();
    this.briefingContent = page.locator("article, main, [data-slot='briefing-content']").first();
  }

  async load() {
    return this.goto('/briefing');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/briefing') && (await this.page.locator('main').isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }
}

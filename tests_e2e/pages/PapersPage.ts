import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class PapersPage extends BasePage {
  readonly pageTitle: Locator;
  readonly searchInput: Locator;
  readonly paperRows: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Papers'), h1:has-text('Paper')").first();
    this.searchInput = page.locator("input[type='search'], input[placeholder*='Search'], input[placeholder*='Suche']").first();
    this.paperRows = page.locator("table tbody tr, [data-slot='paper-item'], a[href^='/papers/']");
  }

  async load() {
    return this.goto('/papers');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/papers') && (await this.page.locator('main').isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }

  async getPapersCount(): Promise<number> {
    try {
      return await this.paperRows.count();
    } catch {
      return 0;
    }
  }

  async openFirstPaper(): Promise<boolean> {
    try {
      const first = this.page.locator("a[href^='/papers/']").first();
      if (await first.isVisible({ timeout: 5000 })) {
        await first.click();
        await this.waitForNetworkIdle();
        return true;
      }
    } catch {
      // Ignored
    }
    return false;
  }
}

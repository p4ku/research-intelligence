import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class DashboardPage extends BasePage {
  readonly pageTitle: Locator;
  readonly statTiles: Locator;
  readonly paperCards: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1, [data-slot='page-title']").first();
    this.statTiles = page.locator("[data-slot='stat-tile'], dl dt");
    this.paperCards = page.locator("article, [data-slot='paper-card'], div.rounded-lg.border");
  }

  async load() {
    return this.goto('/dashboard');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/dashboard') || (await this.page.locator("a[href='/dashboard']").isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }

  async getPapersCount(): Promise<number> {
    try {
      return await this.paperCards.count();
    } catch {
      return 0;
    }
  }
}

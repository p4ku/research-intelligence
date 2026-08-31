import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class ScoringPage extends BasePage {
  readonly pageTitle: Locator;
  readonly formulaBlock: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Scoring')").first();
    this.formulaBlock = page.locator("code, pre, [data-slot='formula-block']").first();
  }

  async load() {
    return this.goto('/scoring');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/scoring') && (await this.page.locator('main').isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }
}

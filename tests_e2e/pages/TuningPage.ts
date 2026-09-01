import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class TuningPage extends BasePage {
  readonly pageTitle: Locator;
  readonly influenceRows: Locator;
  readonly dials: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Tuning')").first();
    // The composition rows: one <dt>/<dd> pair per weighted dimension.
    this.influenceRows = page.locator('main dl > div');
    this.dials = page.locator("main input[type='range']");
  }

  async load() {
    return this.goto('/tuning');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/tuning') && (await this.page.locator('main').isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }

  /** Every dial on the page is non-interactive — the page is read-only by design. */
  async allDialsDisabled(): Promise<boolean> {
    const count = await this.dials.count();
    if (count === 0) return false;
    for (let i = 0; i < count; i++) {
      if (!(await this.dials.nth(i).isDisabled())) return false;
    }
    return true;
  }

  /** The formula itself must never reach the reading app. */
  async showsNoFormulaCode(): Promise<boolean> {
    return (await this.page.locator('main pre, main code').count()) === 0;
  }
}

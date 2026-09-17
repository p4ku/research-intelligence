import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class RunsPage extends BasePage {
  readonly pageTitle: Locator;
  readonly statBand: Locator;
  readonly runRows: Locator;
  readonly noRunsNotice: Locator;

  // Run detail page locators
  readonly runDetailTitle: Locator;
  readonly rerunButton: Locator;
  readonly stopButton: Locator;
  readonly statusPill: Locator;
  readonly stepTimeline: Locator;
  readonly breadcrumbs: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Runs'), h1:has-text('Pipeline')").first();
    this.statBand = page.locator("[data-shape='stat-band'], dl dt");
    this.runRows = page.locator("tr[data-row='run']");
    this.noRunsNotice = page.getByText(/No pipeline runs yet|Keine Pipeline-Läufe/i);

    // Detail elements
    this.runDetailTitle = page.locator("h1:has-text('Run ')").first();
    this.rerunButton = page.locator("button:has-text('Rerun'), button:has-text('Wiederholen')").first();
    this.stopButton = page.locator("button:has-text('Stop'), button:has-text('Stoppen')").first();
    this.statusPill = page.locator("span.inline-flex:has-text('Completed'), span.inline-flex:has-text('Running'), span.inline-flex:has-text('Failed'), span.inline-flex:has-text('Aborted')").first();
    this.stepTimeline = page.locator("section:has-text('Steps'), section:has-text('Schritte')");
    this.breadcrumbs = page.locator("nav[aria-label*='Breadcrumb' i]");
  }

  async load() {
    return this.goto('/runs');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/runs') && (await this.page.locator('main').isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }

  async getRunsCount(): Promise<number> {
    try {
      await this.runRows.first().or(this.noRunsNotice).first().waitFor({ state: 'visible', timeout: 10000 });
      return await this.runRows.count();
    } catch {
      return 0;
    }
  }

  async openFirstRun(): Promise<string | null> {
    const count = await this.getRunsCount();
    if (count === 0) return null;
    const firstRowLink = this.runRows.first().locator("a[href^='/runs/']").first();
    const href = await firstRowLink.getAttribute('href');
    await firstRowLink.click();
    await this.page.waitForURL(/\/runs\/[0-9a-f-]{36}/, { timeout: 15000 });
    await this.waitForNetworkIdle();
    return href;
  }

  async openRunById(runId: string): Promise<void> {
    await this.goto(`/runs/${runId}`);
    await this.waitForNetworkIdle();
  }

  async hasRerunButton(): Promise<boolean> {
    try {
      return await this.rerunButton.isVisible({ timeout: 3000 });
    } catch {
      return false;
    }
  }

  async hasStopButton(): Promise<boolean> {
    try {
      return await this.stopButton.isVisible({ timeout: 3000 });
    } catch {
      return false;
    }
  }

  async getStepCount(): Promise<number> {
    try {
      return await this.page.locator("li[data-shape='step-item'], ol li, [data-row='step']").count();
    } catch {
      return 0;
    }
  }
}

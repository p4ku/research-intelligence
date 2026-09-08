import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class BriefingPage extends BasePage {
  readonly pageTitle: Locator;
  readonly briefingContent: Locator;
  /** The archive ledger's row links — one per briefing, each carrying `?domain=` and `&run=`. */
  readonly editionLinks: Locator;
  /** The edition page's paper cards, each linking to the paper as this run read it (`?run=`). */
  readonly paperCards: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Briefing'), h1:has-text('Briefings')").first();
    this.briefingContent = page.locator("article, main, [data-slot='briefing-content']").first();
    this.editionLinks = page.locator("tr[data-row='briefing'] a[href^='/briefing/']");
    this.paperCards = page.locator("a[data-shape='paper-card']");
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

  /**
   * Opens the first briefing in the archive (the newest). Returns the edition
   * URL (path + query) once its page has loaded, or null when the archive
   * lists nothing to open — a fresh environment with no completed run.
   */
  async openFirstEdition(): Promise<string | null> {
    try {
      // The ledger streams in behind its skeleton (which has rows but no
      // links), so wait for a link rather than reading the first paint.
      await this.editionLinks.first().waitFor({ state: 'visible', timeout: 15000 });
      // The row link is laid over every cell; the leading cells also hold
      // the expand and star controls, positioned above it, so click the
      // row's last cell (the status), which holds nothing else.
      const first = this.page
        .locator("tr[data-row='briefing']")
        .filter({ has: this.page.locator("a[href^='/briefing/']") })
        .first()
        .locator("a[href^='/briefing/']")
        .last();
      const href = await first.getAttribute('href');
      if (!href) return null;
      await first.click();
      await this.page.waitForURL(/\/briefing\/\d{4}-\d{2}-\d{2}/, { timeout: 15000 });
      await this.waitForNetworkIdle();
      const url = new URL(this.currentURL());
      return url.pathname + url.search;
    } catch {
      return null;
    }
  }

  /** The first card's headline score as printed ("43.2"), or null when the edition lists no papers. */
  async firstCardScore(): Promise<string | null> {
    try {
      // Cards stream in after the head; the skeleton's cards are not links.
      const card = this.paperCards.first();
      await card.waitFor({ state: 'visible', timeout: 15000 });
      const text = (await card.innerText()).trim();
      const match = text.match(/^\s*(\d+(?:\.\d+)?|—)/);
      return match ? match[1] : null;
    } catch {
      return null;
    }
  }

  /** Clicks the first card and waits for the paper page. Returns its URL (path + query) or null. */
  async openFirstCard(): Promise<string | null> {
    try {
      const card = this.paperCards.first();
      await card.waitFor({ state: 'visible', timeout: 15000 });
      await card.click();
      await this.page.waitForURL(/\/papers\/[0-9a-f-]{36}/, { timeout: 15000 });
      await this.waitForNetworkIdle();
      const url = new URL(this.currentURL());
      return url.pathname + url.search;
    } catch {
      return null;
    }
  }
}

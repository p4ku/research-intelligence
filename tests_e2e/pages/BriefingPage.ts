import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class BriefingPage extends BasePage {
  readonly pageTitle: Locator;
  readonly briefingContent: Locator;
  /** The archive ledger once it has streamed in (its skeleton has rows but no links). */
  readonly loadedLedger: Locator;
  /** The archive ledger's row links — one per briefing, each carrying `?domain=` and `&run=`. */
  readonly editionLinks: Locator;
  /** The edition page's paper cards, each linking to the paper as this run read it (`?run=`). */
  readonly paperCards: Locator;
  /** The edition page's line when it has no paper cards to show. */
  readonly noPapersNotice: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Briefing'), h1:has-text('Briefings')").first();
    this.briefingContent = page.locator("article, main, [data-slot='briefing-content']").first();
    this.loadedLedger = page.locator("[data-shape='briefing-ledger'][data-state='loaded']").first();
    this.editionLinks = page.locator("tr[data-row='briefing'] a[href^='/briefing/']");
    this.paperCards = page.locator("a[data-shape='paper-card']");
    this.noPapersNotice = page.getByText('No papers are on file for this briefing.');
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
   * URL (path + query) once its page has loaded, or null only when the loaded
   * ledger lists nothing to open — a fresh environment with no completed run.
   * A ledger that never loads, a row without a link or a click that does not
   * navigate throws, so a regression cannot pass as a skip.
   */
  async openFirstEdition(): Promise<string | null> {
    // The ledger streams in behind its skeleton, so wait for the loaded
    // ledger (which also frames the empty state) rather than the first paint.
    await this.loadedLedger.waitFor({ state: 'visible', timeout: 15000 });
    if ((await this.editionLinks.count()) === 0) return null;
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
    if (!href) throw new Error('The first briefing row has no link to its edition.');
    await first.click();
    await this.page.waitForURL(/\/briefing\/\d{4}-\d{2}-\d{2}/, { timeout: 15000 });
    await this.waitForNetworkIdle();
    const url = new URL(this.currentURL());
    return url.pathname + url.search;
  }

  /**
   * The first card's headline score as printed ("43.2"), or null only when
   * the edition says it has no papers on file. Cards stream in after the
   * head; the skeleton's cards are not links, so wait for a card or the notice.
   */
  async firstCardScore(): Promise<string | null> {
    await this.paperCards.first().or(this.noPapersNotice).first().waitFor({ state: 'visible', timeout: 15000 });
    if ((await this.paperCards.count()) === 0) return null;
    const text = (await this.paperCards.first().innerText()).trim();
    const match = text.match(/^\s*(\d+(?:\.\d+)?|—)/);
    if (!match) throw new Error(`The first card does not start with a score: ${JSON.stringify(text.slice(0, 40))}`);
    return match[1];
  }

  /** Clicks the first card and waits for the paper page. Returns its URL (path + query). */
  async openFirstCard(): Promise<string> {
    const card = this.paperCards.first();
    await card.waitFor({ state: 'visible', timeout: 15000 });
    await card.click();
    await this.page.waitForURL(/\/papers\/[0-9a-f-]{36}/, { timeout: 15000 });
    await this.waitForNetworkIdle();
    const url = new URL(this.currentURL());
    return url.pathname + url.search;
  }
}

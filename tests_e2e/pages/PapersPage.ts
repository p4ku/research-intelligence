import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class PapersPage extends BasePage {
  readonly pageTitle: Locator;
  readonly searchInput: Locator;
  readonly paperRows: Locator;
  readonly paginationNav: Locator;
  readonly nextPageButton: Locator;
  readonly prevPageButton: Locator;
  readonly pageNumbers: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Papers'), h1:has-text('Paper')").first();
    this.searchInput = page.locator("input[type='search'], input[placeholder*='Search'], input[placeholder*='Suche']").first();
    this.paperRows = page.locator("table tbody tr, [data-slot='paper-item'], a[href^='/papers/']");
    this.paginationNav = page.locator("nav[aria-label*='pagination'], [data-slot='pagination'], .pagination");
    this.nextPageButton = page.locator("button:has-text('Next'), button:has-text('Weiter'), [aria-label='Next page'], [aria-label='Next']").first();
    this.prevPageButton = page.locator("button:has-text('Previous'), button:has-text('Zurück'), [aria-label='Previous page'], [aria-label='Previous']").first();
    this.pageNumbers = page.locator("nav[aria-label*='pagination'] button, .pagination button");
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

  async hasPagination(): Promise<boolean> {
    try {
      return (await this.paginationNav.isVisible({ timeout: 3000 })) ||
             (await this.nextPageButton.isVisible({ timeout: 3000 }));
    } catch {
      return false;
    }
  }

  async goToNextPage(): Promise<boolean> {
    try {
      if (await this.nextPageButton.isVisible({ timeout: 3000 })) {
        await this.nextPageButton.click();
        await this.waitForNetworkIdle();
        return true;
      }
    } catch {
      // Ignored
    }
    return false;
  }

  async goToPrevPage(): Promise<boolean> {
    try {
      if (await this.prevPageButton.isVisible({ timeout: 3000 })) {
        await this.prevPageButton.click();
        await this.waitForNetworkIdle();
        return true;
      }
    } catch {
      // Ignored
    }
    return false;
  }
}

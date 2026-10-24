import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class AuditQueuePage extends BasePage {
  readonly pageHeading: Locator;
  readonly pendingTabButton: Locator;
  readonly allTabButton: Locator;
  readonly completedTabButton: Locator;
  readonly tableRows: Locator;
  readonly reviewButtons: Locator;

  // Split-Pane Paper Review Workspace Locators
  readonly reviewHeader: Locator;
  readonly paperTitle: Locator;
  readonly stageBadge: Locator;
  readonly progressCounter: Locator;
  readonly leftViewerPane: Locator;
  readonly rightDecisionPane: Locator;
  readonly agreeRadio: Locator;
  readonly overrideRadio: Locator;
  readonly auditorNoteInput: Locator;
  readonly exclusionReasonSelect: Locator;
  readonly submitButton: Locator;
  readonly completionModal: Locator;
  readonly modalReturnButton: Locator;
  readonly modalMonitorRunButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageHeading = page.locator("h1:has-text('Audit Queue'), h1:has-text('Prüfwarteschlange'), h1").first();
    this.pendingTabButton = page.locator("button:has-text('My Pending'), button:has-text('Ausstehend')").first();
    this.allTabButton = page.locator("button:has-text('All Assigned'), button:has-text('Alle zugewiesenen')").first();
    this.completedTabButton = page.locator("button:has-text('Completed History'), button:has-text('Abgeschlossen')").first();
    this.tableRows = page.locator("tbody tr");
    this.reviewButtons = page.locator("tbody tr a button:has-text('Review'), tbody tr a button:has-text('View'), tbody tr a button");

    // Review Workspace
    this.reviewHeader = page.locator("header, div:has-text('Audit Gate'), div:has-text('Gate')").first();
    this.paperTitle = page.locator("h1.text-base, h1.font-bold, h2.font-bold").first();
    this.stageBadge = page.locator("span:has-text('Screening'), span:has-text('Gate'), span:has-text('Extraction')").first();
    this.progressCounter = page.locator("text=/\\d+\\s*\\/\\s*\\d+/").first();
    this.leftViewerPane = page.locator("div:has(iframe), iframe, div:has-text('PDF Document Viewer'), div:has-text('Abstract Content')").first();
    this.rightDecisionPane = page.locator("form, div:has-text('AI Chain-of-Thought Rationale'), div:has-text('Agree with AI Decision')").first();
    this.agreeRadio = page.locator("input[value='agree'], label:has-text('Agree with AI Decision') input").first();
    this.overrideRadio = page.locator("input[value='override_include'], input[value='override_exclude'], label:has-text('Override') input").first();
    this.auditorNoteInput = page.locator("textarea[placeholder*='rationale'], textarea").first();
    this.exclusionReasonSelect = page.locator("select").first();
    this.submitButton = page.locator("button:has-text('Submit'), button:has-text('Update Verdict')").first();
    this.completionModal = page.locator("div:has-text('Audit Checkpoint Complete!')").first();
    this.modalReturnButton = page.locator("button:has-text('Return to Audit Queue'), a:has-text('Return to Audit Queue')").first();
    this.modalMonitorRunButton = page.locator("button:has-text('Monitor Pipeline Run'), a:has-text('Monitor Pipeline Run')").first();
  }

  async isLoaded(): Promise<boolean> {
    try {
      await this.page.waitForURL((url) => url.pathname.includes('/audit-queue'), { timeout: 10_000 });
      await this.waitForNetworkIdle();
      return true;
    } catch {
      return false;
    }
  }

  async getCohortCount(): Promise<number> {
    return await this.tableRows.count();
  }

  async clickFirstReview(): Promise<void> {
    const firstReviewBtn = this.reviewButtons.first();
    await expect(firstReviewBtn).toBeVisible({ timeout: 10_000 });
    await firstReviewBtn.click();
    await this.page.waitForURL((url) => url.pathname.includes('/audit-queue/'), { timeout: 10_000 });
    await this.waitForNetworkIdle();
  }

  async isOnReviewPage(): Promise<boolean> {
    return this.page.url().includes('/audit-queue/') && this.page.url().includes('/papers/');
  }

  async selectAgreeWithAI(): Promise<void> {
    try {
      if (await this.agreeRadio.isVisible({ timeout: 3000 })) {
        await this.agreeRadio.click({ force: true });
      } else {
        await this.page.keyboard.press('KeyA');
      }
    } catch {
      await this.page.keyboard.press('KeyA');
    }
  }

  async submitVerdict(): Promise<void> {
    await expect(this.submitButton).toBeVisible({ timeout: 5000 });
    await this.submitButton.click();
    await this.waitForNetworkIdle();
  }

  async isCompletionModalVisible(): Promise<boolean> {
    try {
      await this.completionModal.waitFor({ state: 'visible', timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }

  async returnToQueue(): Promise<void> {
    if (await this.modalReturnButton.isVisible({ timeout: 3000 })) {
      await this.modalReturnButton.click();
      await this.page.waitForURL((url) => url.pathname === '/audit-queue', { timeout: 8000 });
    } else {
      await this.goto('/audit-queue');
    }
  }
}

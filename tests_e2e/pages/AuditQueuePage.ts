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

  // Extraction Audit Panel Locators
  readonly extractionPanelHeading: Locator;
  readonly verifyAllButton: Locator;
  readonly modifyButton: Locator;
  readonly rejectButton: Locator;
  readonly extractionNoteTextarea: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageHeading = page.locator("h1:has-text('Audit Queue'), h1:has-text('Prüfwarteschlange'), h1").first();
    this.pendingTabButton = page.locator("button:has-text('My Pending'), button:has-text('Ausstehend')").first();
    this.allTabButton = page.locator("button:has-text('All Assigned'), button:has-text('Alle zugewiesenen')").first();
    this.completedTabButton = page.locator("button:has-text('Completed History'), button:has-text('Abgeschlossen')").first();
    this.tableRows = page.locator("tbody tr");
    this.reviewButtons = page.locator("tbody tr a:has-text('Review'), tbody tr a:has-text('View'), tbody tr a[href*='/audit-queue/']");

    // Review Workspace
    this.reviewHeader = page.locator("header:has-text('HITL Systematic Review Audit'), header").first();
    this.paperTitle = page.locator("h2.font-bold, h1.text-base, h1.font-bold, iframe, h2").first();
    this.stageBadge = page.locator("span:has-text('Gate 1'), span:has-text('Gate 2'), span:has-text('Gate 3'), span:has-text('Screening'), span:has-text('Extraction')").first();
    this.progressCounter = page.locator("text=/\\d+\\s*\\/\\s*\\d+/").first();
    this.leftViewerPane = page.locator("div:has(iframe), iframe, div:has-text('PDF Document Viewer'), div:has-text('Abstract Content')").first();
    this.rightDecisionPane = page.locator("div:has-text('AI DECISION'), form, div:has-text('AI Chain-of-Thought Rationale'), div:has-text('Agree with AI Decision')").first();
    this.agreeRadio = page.locator("label:has-text('Agree with AI Decision')").first();
    this.overrideRadio = page.locator("label:has-text('Override')").first();
    this.auditorNoteInput = page.locator("textarea[placeholder*='Explain the specific'], textarea[placeholder*='rationale'], textarea").first();
    this.exclusionReasonSelect = page.locator("select").first();
    this.submitButton = page.locator("button:has-text('Submit & Next Article'), button:has-text('Submit Extraction Audit'), button:has-text('Update Verdict'), button:has-text('Submit')").first();
    this.completionModal = page.locator("h2:has-text('Audit Checkpoint Complete!')");
    this.modalReturnButton = page.locator("a:has-text('Return to Audit Queue'), button:has-text('Return to Audit Queue')").first();
    this.modalMonitorRunButton = page.locator("a:has-text('Monitor Pipeline Run'), button:has-text('Monitor Pipeline Run')").first();

    // Extraction Audit Panel
    this.extractionPanelHeading = page.locator("h3:has-text('AI EXTRACTION AUDIT PANEL'), h3:has-text('EXTRACTION AUDIT')").first();
    this.verifyAllButton = page.locator("button:has-text('Verify All'), button:has-text('All Verified')").first();
    this.modifyButton = page.locator("button:has-text('Modify')").first();
    this.rejectButton = page.locator("button:has-text('Reject')").first();
    this.extractionNoteTextarea = page.locator("textarea[placeholder*='extraction quality'], textarea").first();
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

  async waitForCohort(timeoutMs: number = 240_000, options?: { expectedGate?: string }): Promise<boolean> {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      const pathname = new URL(this.page.url()).pathname;
      if (pathname !== '/audit-queue') {
        await this.goto('/audit-queue');
      } else {
        await this.page.reload();
      }
      await this.waitForNetworkIdle();
      const count = await this.tableRows.count();
      if (count > 0 && (await this.reviewButtons.count()) > 0) {
        if (options?.expectedGate) {
          const tableContent = (await this.page.locator('tbody').first().textContent().catch(() => '')) || '';
          if (tableContent.toLowerCase().includes(options.expectedGate.toLowerCase())) {
            return true;
          }
        } else {
          return true;
        }
      } else if (count === 0 && (await this.allTabButton.isVisible())) {
        await this.allTabButton.click();
        await this.page.waitForTimeout(500);
        if ((await this.tableRows.count()) > 0 && (await this.reviewButtons.count()) > 0) {
          return true;
        }
      }
      await this.page.waitForTimeout(3000);
    }
    return false;
  }

  async waitForWorkspaceCohort(
    workspaceName: string,
    options?: { expectedGate?: string; timeoutMs?: number },
  ): Promise<boolean> {
    const timeoutMs = options?.timeoutMs || 240_000;
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      const pathname = new URL(this.page.url()).pathname;
      if (pathname !== '/audit-queue') {
        await this.goto('/audit-queue');
      } else {
        await this.page.reload();
      }
      await this.waitForNetworkIdle();

      const wsRow = this.tableRows.filter({ hasText: workspaceName });
      const rowCount = await wsRow.count();
      if (rowCount > 0) {
        if (options?.expectedGate) {
          const rowText = (await wsRow.first().textContent()) || '';
          if (rowText.toLowerCase().includes(options.expectedGate.toLowerCase())) {
            const reviewBtn = wsRow.first().locator("a:has-text('Review')");
            if (await reviewBtn.isVisible()) {
              return true;
            }
          }
        } else {
          const reviewBtn = wsRow.first().locator("a:has-text('Review')");
          if (await reviewBtn.isVisible()) {
            return true;
          }
        }
      }
      await this.page.waitForTimeout(3000);
    }
    return false;
  }

  async clickReviewForWorkspace(workspaceName: string): Promise<void> {
    const wsRow = this.tableRows.filter({ hasText: workspaceName }).first();
    const reviewBtn = wsRow.locator("a:has-text('Review')").first();
    await expect(reviewBtn).toBeVisible({ timeout: 15_000 });
    await reviewBtn.click();
    await this.page.waitForURL((url) => url.pathname.includes('/papers/'), { timeout: 25_000 });
    await this.waitForNetworkIdle();
  }

  async clickTableRowForWorkspace(workspaceName: string): Promise<void> {
    const wsRow = this.tableRows.filter({ hasText: workspaceName }).first();
    await expect(wsRow).toBeVisible({ timeout: 15_000 });
    // Click on the table cell rather than the button to test whole-row clickability
    const textCell = wsRow.locator('td').first();
    await textCell.click();
    await this.page.waitForURL((url) => url.pathname.includes('/papers/'), { timeout: 25_000 });
    await this.waitForNetworkIdle();
  }

  async clickFirstReview(): Promise<void> {
    const firstReviewBtn = this.reviewButtons.first();
    await expect(firstReviewBtn).toBeVisible({ timeout: 15_000 });
    await firstReviewBtn.click();
    await this.page.waitForURL((url) => url.pathname.includes('/papers/'), { timeout: 25_000 });
    await this.waitForNetworkIdle();
  }

  async clickTableRowNavigation(rowIndex: number = 0): Promise<void> {
    const row = this.tableRows.nth(rowIndex);
    await expect(row).toBeVisible({ timeout: 15_000 });
    // Click on the text content cell of the row (not directly on the button)
    const titleCell = row.locator('td').first();
    await titleCell.click();
    await this.page.waitForURL((url) => url.pathname.includes('/papers/'), { timeout: 25_000 });
    await this.waitForNetworkIdle();
  }

  async isOnReviewPage(): Promise<boolean> {
    return this.page.url().includes('/audit-queue/') && this.page.url().includes('/papers/');
  }

  async selectAgreeWithAI(): Promise<void> {
    if (await this.agreeRadio.isVisible({ timeout: 2000 })) {
      await this.agreeRadio.click();
    } else {
      await this.page.keyboard.press('KeyA');
    }
    await this.page.waitForTimeout(300);
  }

  async selectOverride(options?: { exclusionReason?: string; note?: string }): Promise<void> {
    if (await this.overrideRadio.isVisible({ timeout: 2000 })) {
      await this.overrideRadio.click();
    } else {
      await this.page.keyboard.press('KeyO');
    }
    await this.page.waitForTimeout(400);

    if (options?.exclusionReason) {
      const select = this.page.locator("select").first();
      if (await select.isVisible({ timeout: 2000 })) {
        try {
          await select.selectOption({ label: options.exclusionReason });
        } catch {
          await select.selectOption({ index: 0 });
        }
      }
    }

    const note = options?.note || 'Auditor override recorded with verified methodology.';
    if (await this.auditorNoteInput.isVisible({ timeout: 2000 })) {
      await this.auditorNoteInput.fill(note);
    }
  }

  async isExtractionStage(): Promise<boolean> {
    try {
      return await this.extractionPanelHeading.isVisible({ timeout: 2000 });
    } catch {
      return false;
    }
  }

  async auditExtraction(options?: { modifyFirst?: boolean; note?: string }): Promise<void> {
    // 1. Click Verify All if visible to default all parameters to clean verification
    if (await this.verifyAllButton.isVisible({ timeout: 2000 })) {
      await this.verifyAllButton.click();
    }

    // 2. Optionally test Modify on first parameter
    if (options?.modifyFirst && (await this.modifyButton.isVisible({ timeout: 2000 }))) {
      await this.modifyButton.click();
      const valueInput = this.page.locator("label:has-text('Corrected Parameter Value') ~ div input, label:has-text('Corrected Parameter Value') + input, input[type='text']").first();
      if (await valueInput.isVisible({ timeout: 2000 })) {
        await valueInput.fill('96.5');
      }
    }

    if (options?.note && (await this.extractionNoteTextarea.isVisible({ timeout: 2000 }))) {
      await this.extractionNoteTextarea.fill(options.note);
    }
  }

  async submitVerdict(): Promise<{ isComplete: boolean }> {
    const currentUrl = this.page.url();
    await expect(this.submitButton).toBeVisible({ timeout: 8000 });

    const submitResponsePromise = this.page.waitForResponse(
      (resp) =>
        resp.url().includes('/submit') &&
        resp.request().method() === 'POST' &&
        resp.status() === 200,
      { timeout: 15_000 }
    );

    await this.submitButton.click();

    const submitResponse = await submitResponsePromise;
    const resData = await submitResponse.json();
    const isComplete = Boolean(resData.is_cohort_complete);

    if (isComplete) {
      await expect(this.completionModal).toBeVisible({ timeout: 8000 });
      return { isComplete: true };
    } else {
      await this.page.waitForURL((url) => url.href !== currentUrl, { timeout: 10_000 });
      await this.waitForNetworkIdle();
      return { isComplete: false };
    }
  }

  async isCompletionModalVisible(): Promise<boolean> {
    try {
      return await this.completionModal.isVisible();
    } catch {
      return false;
    }
  }

  async returnToQueue(): Promise<void> {
    if (await this.modalReturnButton.isVisible({ timeout: 3000 })) {
      await this.modalReturnButton.click();
      await this.page.waitForURL((url) => url.pathname === '/audit-queue', { timeout: 10000 }).catch(() => {});
    }
    if (new URL(this.page.url()).pathname !== '/audit-queue') {
      await this.goto('/audit-queue');
    }
    await this.waitForNetworkIdle();
  }

  async monitorPipelineRun(): Promise<void> {
    if (await this.modalMonitorRunButton.isVisible({ timeout: 3000 })) {
      await this.modalMonitorRunButton.click();
      await this.page.waitForURL((url) => url.pathname.includes('/runs/'), { timeout: 10000 });
      await this.waitForNetworkIdle();
    }
  }
}

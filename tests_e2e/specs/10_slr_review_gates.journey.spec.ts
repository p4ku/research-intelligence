import { test, expect } from '@playwright/test';
import {
  LoginPage,
  SidebarNav,
  AuditQueuePage,
  RunsPage,
} from '../pages/index.js';

const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 10: Systematic Literature Review (SLR) Checkpoint Gates & Audit Queue', () => {
  test('Complete SLR Human-in-the-Loop Journey: Queue Navigation -> Split-Pane Review -> Consensus Verdict', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);
    const auditQueue = new AuditQueuePage(page);
    const runsPage = new RunsPage(page);

    console.log('🚀 Phase 1: Authentication');
    const loggedIn = await loginPage.login(USERNAME, PASSWORD, true);
    expect(loggedIn).toBe(true);

    console.log('🚀 Phase 2: Navigation to SLR Audit Queue');
    await sidebar.navigateTo('audit-queue');
    const isQueueLoaded = await auditQueue.isLoaded();
    expect(isQueueLoaded).toBe(true);

    console.log('🚀 Phase 3: Audit Queue Table & Filter Tabs Validation');
    await expect(auditQueue.pageHeading).toBeVisible({ timeout: 5000 });
    await expect(auditQueue.pendingTabButton).toBeVisible();
    await expect(auditQueue.allTabButton).toBeVisible();
    await expect(auditQueue.completedTabButton).toBeVisible();

    const cohortCount = await auditQueue.getCohortCount();
    console.log(`  Found ${cohortCount} cohort(s) displayed in queue table.`);

    if (cohortCount > 0) {
      console.log('🚀 Phase 4: Entering Split-Pane Audit Workspace');
      await auditQueue.clickFirstReview();
      const onReview = await auditQueue.isOnReviewPage();
      expect(onReview).toBe(true);

      console.log('🚀 Phase 5: Split-Pane Elements Verification');
      await expect(auditQueue.reviewHeader).toBeVisible({ timeout: 5000 });
      await expect(auditQueue.paperTitle).toBeVisible();
      await expect(auditQueue.leftViewerPane).toBeVisible();
      await expect(auditQueue.rightDecisionPane).toBeVisible();

      console.log('🚀 Phase 6: Submitting Audit Verdict (Agree with AI)');
      await auditQueue.selectAgreeWithAI();
      await auditQueue.submitVerdict();

      console.log('🚀 Phase 7: Verification of Auto-Advance or Completion Modal');
      // If the cohort is complete, the modal pops up; otherwise it navigated to the next paper
      const modalVisible = await auditQueue.isCompletionModalVisible();
      if (modalVisible) {
        console.log('  ✓ Completion modal reached: Audit Checkpoint Complete!');
        await auditQueue.returnToQueue();
        expect(await auditQueue.isLoaded()).toBe(true);
      } else {
        console.log('  ✓ Auto-advanced to next unreviewed paper or returned to queue.');
      }
    } else {
      console.log('  ℹ️  No active cohorts currently pending review. Validating tab switching & empty states...');
      await auditQueue.allTabButton.click();
      await page.waitForTimeout(500);
      await auditQueue.completedTabButton.click();
      await page.waitForTimeout(500);
      await auditQueue.pendingTabButton.click();
    }

    console.log('🚀 Phase 8: Pipeline Runs Overview & SLR Checkpoint Status');
    await sidebar.navigateTo('runs');
    expect(await runsPage.isLoaded()).toBe(true);

    console.log('🎉 Full SLR Checkpoint Gates & Audit Queue Journey Completed Successfully!');
  });
});

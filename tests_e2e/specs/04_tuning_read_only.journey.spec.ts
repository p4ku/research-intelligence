import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, TuningPage } from '../pages/index.js';

const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 4: Tuning — what steers the ranking, read-only', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, true);
  });

  test('Reachable from the sidebar, shows the weighting, and adjusts nothing', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const tuning = new TuningPage(page);

    console.log('📍 Step 1: Navigating to Tuning from the sidebar...');
    await sidebar.navigateTo('tuning');
    expect(await tuning.isLoaded()).toBe(true);
    await expect(tuning.pageTitle).toBeVisible();

    console.log('📍 Step 2: The weighting reads as dimensions and their influence...');
    await expect(page.locator('main')).toBeVisible();

    // If current domain has no scores yet, select a domain with scored papers (e.g. Chip Design, Hybrid Computing)
    const emptyNotice = page.getByText(/Nothing has been scored in this domain yet/i);
    if (await emptyNotice.isVisible({ timeout: 2000 })) {
      const activeDomainLink = page.locator("nav a, [data-row='domain'] a").filter({ hasText: /Chip Design|Hybrid Computing|AI/i }).first();
      if (await activeDomainLink.isVisible({ timeout: 2000 })) {
        await activeDomainLink.click();
        await page.waitForTimeout(1000);
      }
    }

    expect(await tuning.influenceRows.count()).toBeGreaterThan(0);

    console.log('📍 Step 3: Every control is disabled — the page is read-only...');
    expect(await tuning.allDialsDisabled()).toBe(true);

    console.log('📍 Step 4: The backend formula is never exposed to the reader...');
    expect(await tuning.showsNoFormulaCode()).toBe(true);

    console.log('  ✅ Tuning page verified as read-only.');
  });
});

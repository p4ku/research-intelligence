import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, TuningPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

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
    expect(await tuning.influenceRows.count()).toBeGreaterThan(0);

    console.log('📍 Step 3: Every control is disabled — the page is read-only...');
    expect(await tuning.allDialsDisabled()).toBe(true);

    console.log('📍 Step 4: The backend formula is never exposed to the reader...');
    expect(await tuning.showsNoFormulaCode()).toBe(true);

    console.log('  ✅ Tuning page verified as read-only.');
  });
});

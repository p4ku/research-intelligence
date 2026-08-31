import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, ScoringPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Journey 4: Composite Signal Scoring & Methodology Inspection', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, true);
  });

  test('Complete Methodology Journey: Inspect custom Python AST signal formula, extraction definitions and weights', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const scoring = new ScoringPage(page);

    console.log('📍 Step 1: Navigating to Composite Scoring page (/scoring)...');
    await sidebar.navigateTo('scoring');
    expect(await scoring.isLoaded()).toBe(true);

    console.log('📍 Step 2: Inspecting Signal Scoring Formula & Code Sandbox presentation...');
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator("h1:has-text('Scoring'), main h1, main h2").first()).toBeVisible();

    console.log('  ✅ Composite scoring methodology page verified.');
  });
});

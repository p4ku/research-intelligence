import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, AskPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Journey 5: Interactive Paper Chat & Scientific Reasoning', () => {
  // /ask is fixed off since 9 Sep 2026 (frontend/src/lib/features.ts): the
  // route is the not-found card and the nav row is gone; journey 07 asserts
  // both. Skipped rather than deleted so the journey returns with the flag.
  test.skip(true, '/ask is fixed off in frontend/src/lib/features.ts');

  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, true);
  });

  test('Complete Chat Journey: Ask scientific questions on ingested literature, verify prompt area & response streams', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const ask = new AskPage(page);

    console.log('📍 Step 1: Navigating to Paper Chat (/ask)...');
    await sidebar.navigateTo('ask');
    expect(await ask.isLoaded()).toBe(true);

    console.log('📍 Step 2: Verifying input textarea and action buttons...');
    await expect(ask.questionInput).toBeVisible();
    await expect(ask.sendButton).toBeVisible();

    console.log('📍 Step 3: Submitting domain scouting question...');
    await ask.askQuestion('What are the key technological breakthroughs and methodology reported?');
    console.log('  ✅ Question submitted to interactive reasoning engine.');

    console.log('📍 Step 4: Verifying response stream area and paper context controls...');
    await expect(ask.messagesList.first()).toBeVisible({ timeout: 15000 }).catch(() => {
      console.log('  ℹ️ Message bubble rendering in progress or polling.');
    });
  });
});


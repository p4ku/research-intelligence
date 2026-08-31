import { test, expect } from '@playwright/test';
import { LoginPage, AskPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Ask / Interactive Paper Chat Journey', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, false);
  });

  test('should load /ask and display question input area', async ({ page }) => {
    const ask = new AskPage(page);
    await ask.load();

    expect(await ask.isLoaded()).toBe(true);
    await expect(ask.questionInput).toBeVisible();
    await expect(ask.sendButton).toBeVisible();
  });
});

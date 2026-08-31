import { test, expect } from '@playwright/test';
import { LoginPage, PapersPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Papers Exploration Journey', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, false);
  });

  test('should load /papers and allow inspecting papers list', async ({ page }) => {
    const papers = new PapersPage(page);
    await papers.load();

    expect(await papers.isLoaded()).toBe(true);

    const count = await papers.getPapersCount();
    if (count > 0) {
      const opened = await papers.openFirstPaper();
      expect(opened).toBe(true);
    }
  });
});

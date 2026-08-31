import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Navigation & Menu Traversing Journey', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, false);
  });

  test('should navigate across all core views in the Next.js frontend', async ({ page }) => {
    const sidebar = new SidebarNav(page);

    const routes = [
      { label: 'dashboard', path: '/dashboard' },
      { label: 'briefing', path: '/briefing' },
      { label: 'papers', path: '/papers' },
      { label: 'scoring', path: '/scoring' },
      { label: 'ask', path: '/ask' },
      { label: 'settings', path: '/settings' },
    ];

    for (const { label, path } of routes) {
      await sidebar.navigateTo(label);
      expect(page.url()).toContain(path);
      await expect(page.locator('main, header')).toBeVisible();
    }
  });
});

import { test, expect } from '@playwright/test';
import { LoginPage, WorkspaceSwitcher } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Workspace Selection Journey', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, false);
  });

  test('should open workspace dropdown and allow switching workspaces', async ({ page }) => {
    const switcher = new WorkspaceSwitcher(page);
    await switcher.goto('/dashboard');

    const availableWorkspaces = await switcher.listAvailableWorkspaces();
    expect(availableWorkspaces.length).toBeGreaterThan(0);

    if (availableWorkspaces.length > 1) {
      const target = availableWorkspaces[1];
      const switched = await switcher.switchToWorkspace(target);
      expect(switched).toBe(true);

      const cookie = await switcher.getCurrentWorkspaceCookie();
      expect(cookie).toBeDefined();
    }
  });
});

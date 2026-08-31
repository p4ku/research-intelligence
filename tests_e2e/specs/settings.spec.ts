import { test, expect } from '@playwright/test';
import { LoginPage, SettingsPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('User Settings Journey (/settings)', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, false);
  });

  test('should load /settings and display profile, password, and workspace cards', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.load();

    expect(await settings.isLoaded()).toBe(true);

    // Profile form
    const profile = await settings.getProfileValues();
    expect(profile.username || profile.email).toBeTruthy();

    // Account role
    const role = await settings.getAccountRole();
    expect(role).toBeTruthy();

    // Password form
    await expect(settings.currentPasswordInput).toBeVisible();
    await expect(settings.newPasswordInput).toBeVisible();
    await expect(settings.confirmPasswordInput).toBeVisible();

    // Workspace section
    const wsMeta = await settings.getWorkspaceMetadata();
    if (wsMeta.name) {
      expect(wsMeta.name.length).toBeGreaterThan(0);
    }
  });
});

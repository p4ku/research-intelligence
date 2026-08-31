import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, SettingsPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Bilingual Language Switcher Journey', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, false);
  });

  test('should toggle language between Deutsch and English in the account menu', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const settings = new SettingsPage(page);

    await settings.load();

    // Toggle to German
    await sidebar.toggleLanguage();

    // Toggle back to English
    await sidebar.toggleLanguage();
  });
});

import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Authentication Journey', () => {
  test('should render login page and reject invalid credentials', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.load();

    expect(await loginPage.isLoaded()).toBe(true);
    await expect(loginPage.signInHeading).toBeVisible();

    // Fill invalid credentials
    await loginPage.fillCredentials('invalid_user_999', 'wrong_pass');
    await loginPage.submit();

    // Verify rejection (stay on login or show error alert)
    await page.waitForTimeout(1000);
    expect(loginPage.currentPath()).toBe('/');
  });

  test('should login with valid test credentials and allow sign out', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);

    // Login
    const loggedIn = await loginPage.login(USERNAME, PASSWORD, true);
    expect(loggedIn).toBe(true);
    expect(page.url()).toContain('/dashboard');

    // Sign out
    await sidebar.signOut();
    expect(await loginPage.isLoaded()).toBe(true);
  });
});

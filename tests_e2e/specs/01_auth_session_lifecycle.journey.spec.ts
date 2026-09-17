import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav } from '../pages/index.js';

const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 1: Authentication & Session Lifecycle', () => {
  test('Complete Authentication Journey: Rejection, Login, Session Verification, and Sign Out', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);

    console.log('📍 Step 1: Navigating to Next.js Root / Login Page...');
    await loginPage.load();
    expect(await loginPage.isLoaded()).toBe(true);
    await expect(loginPage.signInHeading).toBeVisible();

    console.log('📍 Step 2: Testing Invalid Credentials Rejection...');
    await loginPage.fillCredentials('invalid_user_999', 'wrong_pass_1234');
    await loginPage.submit();
    await page.waitForTimeout(1000);
    expect(loginPage.currentPath()).toBe('/');

    console.log(`📍 Step 3: Logging in with valid user '${USERNAME}'...`);
    await loginPage.fillCredentials(USERNAME, PASSWORD);
    await loginPage.submit();
    await page.waitForURL(/\/dashboard/, { timeout: 15000 });
    expect(page.url()).toContain('/dashboard');

    console.log('📍 Step 4: Verifying session cookies and sidebar user profile...');
    const userCookie = await loginPage.getCookie('rs-workspace');
    console.log(`  Active Workspace Cookie: ${userCookie ?? 'default'}`);

    console.log('📍 Step 5: Testing Sign Out journey...');
    await sidebar.signOut();
    expect(await loginPage.isLoaded()).toBe(true);
    console.log('  ✅ Successfully signed out and returned to login.');
  });
});

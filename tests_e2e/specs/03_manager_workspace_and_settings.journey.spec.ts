import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, WorkspaceSwitcher, SettingsPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Journey 3: Workspace Multi-Tenancy, Settings & Locale Management', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, true);
  });

  test('Complete Manager Journey: Switch workspaces -> Verify settings (/settings) -> Toggle bilingual locale', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const switcher = new WorkspaceSwitcher(page);
    const settings = new SettingsPage(page);

    console.log('📍 Step 1: Listing accessible workspaces in Dropdown...');
    const available = await switcher.listAvailableWorkspaces();
    console.log(`  Found ${available.length} workspace(s):`, available);
    expect(available.length).toBeGreaterThan(0);

    if (available.length > 1) {
      console.log(`📍 Step 2: Switching to alternate workspace '${available[1]}'...`);
      const switched = await switcher.switchToWorkspace(available[1]);
      expect(switched).toBe(true);
      const cookie = await switcher.getCurrentWorkspaceCookie();
      console.log(`  Updated rs-workspace cookie: ${cookie}`);
    }

    console.log('📍 Step 3: Navigating to User Settings (/settings)...');
    await settings.load();
    expect(await settings.isLoaded()).toBe(true);

    console.log('📍 Step 4: Inspecting Profile, Account details and Password form...');
    const profile = await settings.getProfileValues();
    console.log('  Profile Values:', profile);
    expect(profile.username || profile.email).toBeTruthy();

    const role = await settings.getAccountRole();
    console.log(`  Account Role: ${role}`);
    expect(role).toBeTruthy();

    const signedInWith = await settings.getSignedInWith();
    console.log(`  Signed in with: ${signedInWith}`);
    expect(signedInWith).toBeTruthy();

    // Settings is profile / account / password only; the domain and
    // notification cards were removed, so the password form is the last card.
    const passwordFormVisible = await settings.isPasswordFormVisible();
    console.log(`  Password form visible: ${passwordFormVisible}`);
    expect(passwordFormVisible).toBe(true);

    console.log('📍 Step 5: Testing Bilingual Locale Switcher (EN <-> DE)...');
    await sidebar.toggleLanguage();
    console.log('  Toggled language to German.');
    await sidebar.toggleLanguage();
    console.log('  Restored language to English.');
  });
});

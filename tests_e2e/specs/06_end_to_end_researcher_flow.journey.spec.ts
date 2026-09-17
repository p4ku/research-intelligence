import { test, expect } from '@playwright/test';
import {
  LoginPage,
  SidebarNav,
  DashboardPage,
  BriefingPage,
  SettingsPage,
  WorkspaceSwitcher,
} from '../pages/index.js';

const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 6: Full End-to-End Researcher Journey (Comprehensive)', () => {
  test('Complete Researcher Flow: Auth -> Dashboard -> Briefings -> Settings -> Logout', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);
    const dashboard = new DashboardPage(page);
    const briefing = new BriefingPage(page);
    const settings = new SettingsPage(page);
    const switcher = new WorkspaceSwitcher(page);

    console.log('🚀 Phase 1: Authentication');
    const loggedIn = await loginPage.login(USERNAME, PASSWORD, true);
    expect(loggedIn).toBe(true);

    console.log('🚀 Phase 2: Today Dashboard Review');
    await sidebar.navigateTo('dashboard');
    expect(await dashboard.isLoaded()).toBe(true);

    console.log('🚀 Phase 3: Executive Briefing Reading');
    await sidebar.navigateTo('briefing');
    expect(await briefing.isLoaded()).toBe(true);

    // Phases 4 (/papers) and 5 (/ask) are gone: both routes are fixed off
    // since 9 Sep 2026 (frontend/src/lib/features.ts) and journey 07 asserts
    // their absence. navigateTo() would have landed on the not-found card.

    console.log('🚀 Phase 6: Workspace Switching');
    const workspaces = await switcher.listAvailableWorkspaces();
    console.log(`  Accessible Workspaces (${workspaces.length}):`, workspaces);

    console.log('🚀 Phase 7: User Settings & Profile Verification');
    await sidebar.navigateTo('settings');
    expect(await settings.isLoaded()).toBe(true);
    const profile = await settings.getProfileValues();
    console.log('  Profile Data:', profile);

    console.log('🚀 Phase 8: Sign Out');
    await sidebar.signOut();
    expect(await loginPage.isLoaded()).toBe(true);
    console.log('🎉 Full End-to-End User Journey Completed Successfully!');
  });
});

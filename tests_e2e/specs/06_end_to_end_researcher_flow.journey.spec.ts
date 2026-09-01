import { test, expect } from '@playwright/test';
import {
  LoginPage,
  SidebarNav,
  DashboardPage,
  BriefingPage,
  PapersPage,
  AskPage,
  SettingsPage,
  WorkspaceSwitcher,
} from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Journey 6: Full End-to-End Researcher Journey (Comprehensive)', () => {
  test('Complete Researcher Flow: Auth -> Dashboard -> Briefings -> Papers -> Ask Chat -> Settings -> Logout', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);
    const dashboard = new DashboardPage(page);
    const briefing = new BriefingPage(page);
    const papers = new PapersPage(page);
    const ask = new AskPage(page);
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

    console.log('🚀 Phase 4: Systematic Papers Exploration');
    await sidebar.navigateTo('papers');
    expect(await papers.isLoaded()).toBe(true);

    console.log('🚀 Phase 5: Ask / Paper Chat');
    await sidebar.navigateTo('ask');
    expect(await ask.isLoaded()).toBe(true);

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

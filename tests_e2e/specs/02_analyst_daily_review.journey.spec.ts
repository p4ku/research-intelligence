import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, DashboardPage, BriefingPage, PapersPage } from '../pages/index.js';

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

test.describe('Journey 2: Analyst Daily Review & Literature Scouting', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, true);
  });

  test('Complete Daily Review Journey: Dashboard metrics -> Briefing reading -> Papers exploration & scorecard inspection', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const dashboard = new DashboardPage(page);
    const briefing = new BriefingPage(page);
    const papers = new PapersPage(page);

    console.log('📍 Step 1: Inspecting Dashboard (Today view)...');
    await sidebar.navigateTo('dashboard');
    expect(await dashboard.isLoaded()).toBe(true);
    const visiblePapers = await dashboard.getPapersCount();
    console.log(`  Dashboard papers surfaced: ${visiblePapers}`);

    console.log('📍 Step 2: Navigating to Executive Briefings (/briefing)...');
    await sidebar.navigateTo('briefing');
    expect(await briefing.isLoaded()).toBe(true);
    await expect(page.locator('main')).toBeVisible();

    console.log('📍 Step 2b: Opening the newest briefing and one of its papers...');
    // A briefing's permalink names its day, domain and run (a domain can
    // brief twice in a day), and every card carries the run so the paper
    // page opens on the score the card shows, with a way back to the edition.
    const editionUrl = await briefing.openFirstEdition();
    if (!editionUrl) {
      console.log('  ⏭ SKIPPED: no briefing to open (no completed run with papers in this environment).');
    } else {
      expect(editionUrl).toMatch(/^\/briefing\/\d{4}-\d{2}-\d{2}\?domain=[0-9a-f-]{36}&run=[0-9a-f-]{36}$/);
      const run = new URL(editionUrl, 'http://e2e').searchParams.get('run');
      const cardScore = await briefing.firstCardScore();
      if (cardScore === null) {
        console.log('  ⏭ SKIPPED: the briefing lists no papers.');
      } else {
        const paperUrl = await briefing.openFirstCard();
        expect(paperUrl).toMatch(/^\/papers\/[0-9a-f-]{36}\?run=/);
        expect(new URL(paperUrl, 'http://e2e').searchParams.get('run')).toBe(run);
        // The rail streams in behind a skeleton of the same shape, so read
        // the loaded one and let the assertion retry until it has painted.
        const pageScore = page
          .locator("[data-shape='score-rail'][data-state='loaded'] [data-row='score'] > span")
          .first();
        await expect(pageScore).toHaveText(cardScore);
        const back = page.locator("[data-shape='paper-nav'] [data-row='back'] a");
        await expect(back).toHaveAttribute('href', editionUrl);
        console.log(`  ✅ Paper opened at ${cardScore} (as the card showed); back link returns to the edition.`);
      }
      await sidebar.navigateTo('briefing');
      expect(await briefing.isLoaded()).toBe(true);
    }

    console.log('📍 Step 3: Navigating to Systematic Papers Explorer (/papers)...');
    await sidebar.navigateTo('papers');
    expect(await papers.isLoaded()).toBe(true);
    const paperCount = await papers.getPapersCount();
    console.log(`  Total Ingested Papers listed: ${paperCount}`);

    console.log('📍 Step 4: Inspecting Paper detail view & parameter extraction scorecards...');
    if (paperCount > 0) {
      const opened = await papers.openFirstPaper();
      expect(opened).toBe(true);
      console.log('  ✅ Opened paper detail view and verified parameters/scores.');
    }
  });
});

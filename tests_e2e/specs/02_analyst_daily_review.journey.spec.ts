import { test, expect } from '@playwright/test';
import { LoginPage, SidebarNav, DashboardPage, BriefingPage } from '../pages/index.js';

const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 2: Analyst Daily Review & Literature Scouting', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(USERNAME, PASSWORD, true);
  });

  test('Complete Daily Review Journey: Dashboard metrics -> Briefing reading -> Papers exploration & scorecard inspection', async ({ page }) => {
    const sidebar = new SidebarNav(page);
    const dashboard = new DashboardPage(page);
    const briefing = new BriefingPage(page);

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

        // Navigate back to the edition using the back link
        await back.click();
        await page.waitForURL(/\/briefing\/\d{4}-\d{2}-\d{2}/, { timeout: 10000 });
        await briefing.waitForNetworkIdle();
        console.log('  ✅ Returned to briefing edition.');
      }

      // Step 2c: Server-side pagination & pager checks
      console.log(`📍 Step 2c: Testing Pagination on edition '${editionUrl}'...`);
      const hasPager = await briefing.hasPagination();
      if (hasPager) {
        const p1 = await briefing.getActivePage();
        expect(p1).toBe(1);
        console.log('  • Page 1 is active by default.');

        const page2Btn = page.locator("nav[aria-label*='agin' i] button:has-text('2')").first();
        if (await page2Btn.isVisible()) {
          console.log('  • Clicking page 2...');
          await briefing.clickPage(2);
          expect(page.url()).toContain('page=2');
          const p2 = await briefing.getActivePage();
          expect(p2).toBe(2);
          const cardsP2 = await briefing.getCardsCount();
          expect(cardsP2).toBeGreaterThan(0);
          console.log(`  ✅ Successfully transitioned to Page 2 (${cardsP2} cards rendered).`);

          console.log('  • Returning to page 1...');
          await briefing.clickPage(1);
          const p1Back = await briefing.getActivePage();
          expect(p1Back).toBe(1);
          console.log('  ✅ Successfully returned to Page 1.');
        }
      } else {
        console.log('  • Briefing papers fit on one page without pager (count <= 20).');
        const page2Url = editionUrl.includes('?') ? `${editionUrl}&page=2` : `${editionUrl}?page=2`;
        console.log(`  • Validating server pagination route with direct page=2 URL: ${page2Url}...`);
        await page.goto(page2Url, { waitUntil: 'domcontentloaded' });
        await briefing.waitForNetworkIdle();
        expect(page.url()).toContain('page=2');
        console.log('  ✅ Server accepted page=2 query parameter.');

        await page.goto(editionUrl, { waitUntil: 'domcontentloaded' });
        await briefing.waitForNetworkIdle();
      }

      // Step 2d: Screening Log navigation (scope=excluded)
      console.log('📍 Step 2d: Testing Screening Log navigation (scope=excluded)...');
      const screeningLogLink = page.locator("a[href*='/run']").filter({ hasText: /Screening/i }).first();
      if (await screeningLogLink.isVisible({ timeout: 4000 })) {
        const logUrl = await briefing.openScreeningLog();
        expect(logUrl).toMatch(/\/briefing\/\d{4}-\d{2}-\d{2}\/run/);
        console.log(`  ✅ Screening Log page loaded: ${logUrl}`);

        const statItems = page.locator("main dt, main dd, main div:has-text('Screened'), main div:has-text('Gefiltert')");
        expect(await statItems.count()).toBeGreaterThan(0);
        console.log('  ✅ Screening log funnel stats verified.');

        // Navigate back to the edition
        const breadcrumbToBriefing = page.locator("nav[aria-label*='Breadcrumb' i] a[href*='/briefing/']").filter({ hasNotText: /^Briefings?$/ }).first();
        if (await breadcrumbToBriefing.isVisible()) {
          await breadcrumbToBriefing.click();
          await page.waitForURL((url) => !url.pathname.includes('/run'), { timeout: 10000 });
          await briefing.waitForNetworkIdle();
          console.log('  ✅ Breadcrumb navigated back to briefing edition.');
        } else {
          await page.goto(editionUrl, { waitUntil: 'domcontentloaded' });
          await briefing.waitForNetworkIdle();
        }
      } else {
        console.log('  • No screening log link present.');
      }

      // Step 2e: Sort Options & Score Filter Rail
      console.log('📍 Step 2e: Testing Sort Options Rail...');
      const sortOption = page.locator("aside button[aria-pressed]").first();
      await sortOption.waitFor({ state: 'visible', timeout: 10000 });
      const sortButtons = page.locator("aside button[aria-pressed]");
      const count = await sortButtons.count();
      console.log(`  • Found ${count} sort option buttons in aside rail.`);
      expect(count).toBeGreaterThan(0);

      // Click the second available sort option if multiple exist, else first
      const targetSort = count > 1 ? sortButtons.nth(1) : sortButtons.first();
      const sortLabel = (await targetSort.innerText()).trim();
      console.log(`  • Clicking sort option '${sortLabel}'...`);
      await targetSort.click();
      await expect(targetSort).toHaveAttribute('aria-pressed', 'true', { timeout: 5000 });
      if (count > 1) {
        await expect(page).toHaveURL(/sort=/, { timeout: 10000 });
      }
      console.log(`  ✅ Sort option applied, URL updated to: ${page.url()}`);

      await sidebar.navigateTo('briefing');
      expect(await briefing.isLoaded()).toBe(true);
    }
  });
});


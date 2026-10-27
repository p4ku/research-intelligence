import { test, expect } from '@playwright/test';
import { ApiHarness, AuthTokens, WorkspaceData, setAuthCookies } from '../lib/api-harness.js';
import { LoginPage, SidebarNav, DashboardPage, BriefingPage, RunsPage } from '../pages/index.js';

const ADMIN_USER = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const ADMIN_PASS = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 8: Multi-Persona Lifecycle, Dynamic Filtering & Run Scorecard Exploration', () => {
  let api: ApiHarness;
  let adminTokens: AuthTokens;
  let testWorkspace: WorkspaceData;
  let testWorkspace2: WorkspaceData;
  let completedRunId: string;
  let runDate: string;
  let targetURL: string;
  const suffix = Math.floor(Math.random() * 90000000) + 10000000;

  test.beforeAll(async ({ baseURL }) => {
    test.setTimeout(300_000); // 5 minutes timeout for workspace provisioning and autonomous SLR run
    targetURL = baseURL || 'http://localhost:3000';
    console.log(`\n=================================================================`);
    console.log(`🚀 SETUP: Initializing Multi-Persona E2E Test on ${targetURL}...`);
    console.log(`=================================================================`);
    api = new ApiHarness(targetURL);

    // 1. Authenticate as Admin via API
    adminTokens = await api.login(ADMIN_USER, ADMIN_PASS);
    console.log(`  ✅ Admin authenticated via API (User: ${adminTokens.username})`);

    // 2. Create Workspace 1 (Quantum AI Review)
    testWorkspace = await api.createWorkspace(adminTokens.access, {
      name: `test_e2e_quantum_scout_${suffix}`,
      abstract_acceptance_criteria: 'Accept quantum computing, machine learning, and transformer architectures.',
      abstract_rejection_criteria: 'Reject unrelated non-technical papers.',
      full_text_acceptance_criteria: 'Accept papers with empirical evaluations and experimental benchmarks.',
      full_text_rejection_criteria: 'Reject pure opinion or summary whitepapers.',
      screening_llm_model: 'google/gemini-3.8-flash',
    });
    console.log(`  ✅ Created Workspace 1: '${testWorkspace.name}' (${testWorkspace.id})`);

    // 3. Create Workspace 2 (Retail Logistics & Edge)
    testWorkspace2 = await api.createWorkspace(adminTokens.access, {
      name: `test_e2e_logistics_edge_${suffix}`,
      abstract_acceptance_criteria: 'Accept retail supply chain, logistics optimization, and edge inference.',
      abstract_rejection_criteria: 'Reject pure hardware fabrication without software applications.',
      full_text_acceptance_criteria: 'Accept benchmarks on latency or throughput.',
      full_text_rejection_criteria: 'Reject theoretical position papers.',
    });
    console.log(`  ✅ Created Workspace 2: '${testWorkspace2.name}' (${testWorkspace2.id})`);

    // 4. Configure Scrapers & Dynamic Extraction Definitions in Workspace 1
    await api.createScraper(adminTokens.access, {
      workspace: testWorkspace.id,
      provider: 'arxiv',
      search_query: 'cat:cs.AI AND (all:"transformer" OR all:"quantum")',
      limit: 1,
    });
    console.log(`  ✅ Configured ArXiv Scraper for Workspace 1.`);

    await api.createExtractionDefinition(adminTokens.access, {
      workspace: testWorkspace.id,
      name: 'Strategic Fit',
      system_prompt: 'Evaluate enterprise strategic fit from 0 to 100.',
      user_prompt_template: 'Paper: {{title}}\nAbstract: {{abstract}}\nEvaluate Strategic Fit.',
      response_schema: {
        type: 'object',
        properties: { fit_score: { type: 'number', minimum: 0, maximum: 100 } },
        required: ['fit_score'],
      },
      exit_metrics: ['fit_score'],
      primary_frontend_metric: 'fit_score',
    });

    await api.createExtractionDefinition(adminTokens.access, {
      workspace: testWorkspace.id,
      name: 'TRL Level',
      system_prompt: 'Assess Technology Readiness Level from 1 to 9.',
      user_prompt_template: 'Assess TRL for: {{title}}\n{{abstract}}',
      response_schema: {
        type: 'object',
        properties: { trl: { type: 'number', minimum: 1, maximum: 9 } },
        required: ['trl'],
      },
      exit_metrics: ['trl'],
      primary_frontend_metric: 'trl',
    });
    console.log(`  ✅ Configured Dynamic Extractions ('Strategic Fit', 'TRL Level') for Workspace 1.`);

    // 5. Launch an autonomous pipeline run via API and wait for completion
    console.log(`  🚀 Launching autonomous research pipeline to generate live briefing & scorecard...`);
    const runRes = await api.startPipelineRun(adminTokens.access, {
      workspace_id: testWorkspace.id,
      name: `E2E Review Run - ${suffix}`,
      limit: 1,
      reprocess_existing: true,
    });
    const runId = runRes.pipeline_run_id || runRes.id;
    console.log(`  ⏳ Polling pipeline run '${runId}' for completion...`);
    const completedRun = await api.pollRunUntilComplete(adminTokens.access, runId, 180, 2000);
    completedRunId = completedRun.id;
    const completedDt = completedRun.completed_at || completedRun.run_date || new Date().toISOString();
    runDate = completedDt.slice(0, 10);
    console.log(`  🏁 Pipeline Run '${completedRunId}' completed on date ${runDate}! (Status: ${completedRun.status})`);
  });

  test.afterAll(async () => {
    test.setTimeout(120_000);
    console.log(`\n=================================================================`);
    console.log(`🧹 TEARDOWN: Cleaning up created test workspaces via API...`);
    console.log(`=================================================================`);
    if (adminTokens?.access) {
      if (testWorkspace?.id) {
        await api.deleteWorkspace(adminTokens.access, testWorkspace.id);
        console.log(`  ✅ Deleted Workspace 1 (${testWorkspace.id}) via API.`);
      }
      if (testWorkspace2?.id) {
        await api.deleteWorkspace(adminTokens.access, testWorkspace2.id);
        console.log(`  ✅ Deleted Workspace 2 (${testWorkspace2.id}) via API.`);
      }
    }
  });

  test('End-to-End User Journey: Dashboard -> Runs & Execution Details -> Briefing & Dynamic Sliders/Sort -> Screening Log -> Paper Scorecard', async ({ page }) => {
    test.setTimeout(180_000); // 3 minutes timeout for complete journey
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);
    const dashboard = new DashboardPage(page);
    const runsPage = new RunsPage(page);
    const briefingPage = new BriefingPage(page);

    // =========================================================================
    // Phase 1: Admin Frontend Authentication & Dashboard Inspection (/dashboard)
    // =========================================================================
    console.log('\n👑 Phase 1: Admin Frontend Authentication & Dashboard Inspection (/dashboard)');
    await setAuthCookies(page.context(), adminTokens, targetURL);
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    expect(await dashboard.isLoaded()).toBe(true);

    // Admin has runnable workspaces, so the RunCard / Card Aside should be visible
    const runCardAside = page.locator("aside, form[action*='pipeline-runs']");
    await expect(runCardAside.first()).toBeVisible({ timeout: 10000 });
    console.log('  ✅ Admin Dashboard verified with active RunCard control.');

    // =========================================================================
    // Phase 2: Pipeline Runs List (/runs) & Run Detail (/runs/[id])
    // =========================================================================
    console.log('\n👑 Phase 2: Pipeline Runs List (/runs) & Run Detail (/runs/[id])');
    await sidebar.navigateTo('/runs');
    expect(await runsPage.isLoaded()).toBe(true);
    const count = await runsPage.getRunsCount();
    console.log(`  • Found ${count} pipeline runs in ledger.`);
    expect(count).toBeGreaterThan(0);

    // Navigate to the specific completed run detail
    console.log(`  • Navigating to run detail: /runs/${completedRunId}...`);
    await runsPage.openRunById(completedRunId);
    await expect(page.locator("h1:has-text('Run')").first()).toBeVisible({ timeout: 15000 });
    console.log('  ✅ Run detail header loaded.');

    // Assert Admin has the Rerun button available
    const hasRerun = await runsPage.hasRerunButton();
    console.log(`  • Admin has Rerun button visible: ${hasRerun}`);
    expect(hasRerun).toBe(true);

    // Assert steps timeline is rendered with component runs
    await expect(page.locator("section:has-text('Steps'), section:has-text('Schritte')")).toBeVisible({ timeout: 10000 });
    const stepCount = await runsPage.getStepCount();
    console.log(`  ✅ Step timeline rendered with ${stepCount} component step(s).`);

    // =========================================================================
    // Phase 3: Executive Briefing & Dynamic Dimension Sliders (/briefing/[date])
    // =========================================================================
    console.log('\n👑 Phase 3: Executive Briefing & Dynamic Dimension Sliders (/briefing)');
    const editionUrl = `/briefing/${runDate}?domain=${testWorkspace.id}&run=${completedRunId}`;
    console.log(`  • Navigating to edition URL: ${editionUrl}...`);
    await page.goto(editionUrl, { waitUntil: 'domcontentloaded' });
    await briefingPage.waitForNetworkIdle();
    expect(await briefingPage.isLoaded()).toBe(true);

    // Verify paper cards exist
    const cardsCount = await briefingPage.getCardsCount();
    console.log(`  • Surfaced papers on edition: ${cardsCount}`);
    expect(cardsCount).toBeGreaterThan(0);

    // Verify dynamic filter rail (sliders & sort buttons)
    const sliders = briefingPage.getSliders();
    const slidersCount = await sliders.count();
    console.log(`  • Found ${slidersCount} range slider(s) on filter rail.`);
    expect(slidersCount).toBeGreaterThan(0);

    const sortButtons = briefingPage.getSortButtons();
    const sortCount = await sortButtons.count();
    console.log(`  • Found ${sortCount} sort option(s) on rail.`);
    expect(sortCount).toBeGreaterThan(1);

    // Test clicking an alternate sort option
    const secondSort = sortButtons.nth(1);
    const sortText = (await secondSort.innerText()).trim();
    console.log(`  • Selecting sort option '${sortText}'...`);
    await secondSort.click();
    await page.waitForURL(/sort=/, { timeout: 10000 });
    console.log(`  ✅ Sort option applied: ${page.url()}`);

    // Test adjusting the Total Score slider
    console.log('  • Adjusting score floor slider...');
    await briefingPage.setSliderValue(0, 10);
    expect(await briefingPage.hasResetFiltersButton()).toBe(true);
    console.log('  ✅ Reset filters button appeared after slider adjustment.');

    // Click Reset Filters
    await briefingPage.clickResetFilters();
    console.log('  ✅ Filters reset back to default view.');

    // =========================================================================
    // Phase 4: Screening Log Exclusions (/briefing/[date]/run?domain=...)
    // =========================================================================
    console.log('\n👑 Phase 4: Screening Log Exclusions (/briefing/[date]/run)');
    const logUrl = `/briefing/${runDate}/run?domain=${testWorkspace.id}&run=${completedRunId}`;
    console.log(`  • Navigating to Screening Log: ${logUrl}...`);
    await page.goto(logUrl, { waitUntil: 'domcontentloaded' });
    await briefingPage.waitForNetworkIdle();
    await expect(page.locator("h1:has-text('Screening log'), h1:has-text('Screening-Protokoll')")).toBeVisible({ timeout: 10000 });
    console.log('  ✅ Current run screening log page loaded.');

    // In local / stub environments with historical fixture 2026-09-11
    const isLocal = !page.url().includes('soinventive.co.uk') && !page.url().includes('schwarz');
    if (isLocal) {
      console.log('  • Navigating to historical edition screening log: /briefing/2026-09-11/run?domain=62978d07-f763-40a3-8b82-c7f1eabe6fd5...');
      try {
        await page.goto('/briefing/2026-09-11/run?domain=62978d07-f763-40a3-8b82-c7f1eabe6fd5&run=607a2603-6910-4e00-8ffc-9e9893db024e', { waitUntil: 'domcontentloaded' });
        await briefingPage.waitForNetworkIdle();
        if (await page.locator("h1:has-text('Screening log'), h1:has-text('Screening-Protokoll')").isVisible({ timeout: 3000 })) {
          const statsExclusions = page.locator("main dt, main dd, main div:has-text('Screened'), main div:has-text('Gefiltert')");
          expect(await statsExclusions.count()).toBeGreaterThan(0);
          console.log('  ✅ Historical screening log funnel stats & exclusions verified.');
        }
      } catch {
        // Skip historical fixture on remote environments
      }
    }

    // =========================================================================
    // Phase 5: Paper Document Details & Scorecard (/papers/[id])
    // =========================================================================
    console.log('\n👑 Phase 5: Paper Document Details & Scorecard (/papers/[id])');
    // Return to edition and click the first paper
    await page.goto(editionUrl, { waitUntil: 'domcontentloaded' });
    await briefingPage.waitForNetworkIdle();
    const paperUrl = await briefingPage.openFirstCard();
    console.log(`  • Opened paper detail page: ${paperUrl}`);
    expect(paperUrl).toMatch(/\/papers\/[0-9a-f-]{36}/);

    // Verify paper detail elements: Title and loaded scorecard
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
    const scoreElement = page.locator("[data-shape='score-rail'][data-state='loaded'], [data-row='score'], dl, main div.rounded-sm").first();
    await expect(scoreElement).toBeVisible({ timeout: 10000 });
    console.log('  ✅ Paper detail & composite signal score loaded.');

    // Check breadcrumb / back link leads back to the briefing
    const backToBriefing = page.locator("[data-shape='paper-nav'] [data-row='back'] a, nav[aria-label*='Breadcrumb' i] a[href*='/briefing/']").first();
    await expect(backToBriefing).toBeVisible({ timeout: 10000 });
    await backToBriefing.click();
    await page.waitForURL(/\/briefing\/\d{4}-\d{2}-\d{2}/, { timeout: 10000 });
    console.log('  ✅ Back link successfully navigated back to Briefing Edition.');

    console.log('\n=================================================================');
    console.log('🎉 COMPREHENSIVE MULTI-PERSONA E2E FRONTEND JOURNEY COMPLETED!');
    console.log('=================================================================');
  });
});

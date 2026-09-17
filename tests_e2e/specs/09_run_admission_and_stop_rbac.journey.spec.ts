import { test, expect } from '@playwright/test';
import { ApiHarness, AuthTokens, WorkspaceData, setAuthCookies } from '../lib/api-harness.js';
import { SidebarNav, DashboardPage, RunsPage } from '../pages/index.js';

const ADMIN_USER = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
const ADMIN_PASS = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

test.describe('Journey 9: Frontend Pipeline Run Admission, UI Launch & Admin-Only Stop Flow', () => {
  let api: ApiHarness;
  let adminTokens: AuthTokens;
  let testWorkspace: WorkspaceData;
  let launchedRunId: string;
  let targetURL: string;
  const suffix = Math.floor(Math.random() * 90000000) + 10000000;

  test.beforeAll(async ({ baseURL }) => {
    test.setTimeout(180_000);
    targetURL = baseURL || 'http://localhost:3000';
    console.log(`\n=================================================================`);
    console.log(`🚀 SETUP: Initializing Run Admission & Stop Journey on ${targetURL}...`);
    console.log(`=================================================================`);
    api = new ApiHarness(targetURL);

    // 1. Authenticate as Admin via API
    adminTokens = await api.login(ADMIN_USER, ADMIN_PASS);
    console.log(`  ✅ Admin authenticated via API (User: ${adminTokens.username})`);

    // 2. Create dedicated workspace for UI launch and stop testing
    testWorkspace = await api.createWorkspace(adminTokens.access, {
      name: `test_e2e_launch_stop_${suffix}`,
      abstract_acceptance_criteria: 'Accept quantum computing, machine learning, and hardware architectures.',
      abstract_rejection_criteria: 'Reject unrelated non-technical papers.',
      full_text_acceptance_criteria: 'Accept papers with empirical evaluations.',
      full_text_rejection_criteria: 'Reject pure opinion or summary whitepapers.',
      screening_llm_model: 'google/gemini-3.8-flash',
    });
    console.log(`  ✅ Created Workspace: '${testWorkspace.name}' (${testWorkspace.id})`);

    // 3. Configure Scraper so pipeline has target literature
    await api.createScraper(adminTokens.access, {
      workspace: testWorkspace.id,
      provider: 'arxiv',
      search_query: 'cat:cs.AI AND "transformer architecture"',
      limit: 10,
    });
    console.log(`  ✅ Configured ArXiv Scraper for Workspace.`);
  });

  test.afterAll(async () => {
    test.setTimeout(60_000);
    console.log(`\n=================================================================`);
    console.log(`🧹 TEARDOWN: Cleaning up test workspace via API...`);
    console.log(`=================================================================`);
    if (adminTokens?.access && testWorkspace?.id) {
      await api.deleteWorkspace(adminTokens.access, testWorkspace.id);
      console.log(`  ✅ Deleted Workspace (${testWorkspace.id}) via API.`);
    }
  });

  test('Persona Permission Checks: Researcher Blocked -> Run Launched -> Admin Stops Run -> Rerun Available', async ({ page }) => {
    test.setTimeout(180_000);
    const dashboard = new DashboardPage(page);

    // =========================================================================
    // Step 1: Verify Researcher / Unprivileged Boundary (Forbidden 401/403)
    // =========================================================================
    console.log('\n🔬 Step 1: Verifying Researcher Launch Boundary (Forbidden 401/403)...');
    const unprivilegedStartRes = await page.request.post('/bff/pipeline-runs/start', {
      data: {
        workspace_id: testWorkspace.id,
        start_date: '2026-08-01',
        end_date: '2026-08-31',
      },
    });
    expect([401, 403]).toContain(unprivilegedStartRes.status());
    console.log(`  🛡️ Unprivileged / Researcher launch attempt blocked with HTTP ${unprivilegedStartRes.status()}.`);

    // =========================================================================
    // Step 2: Inject Admin Auth Cookies & Inspect Dashboard RunCard (/dashboard)
    // =========================================================================
    console.log('\n👑 Step 2: Admin Session Cookie Injection & Dashboard RunCard Inspection (/dashboard)...');
    await setAuthCookies(page.context(), adminTokens, targetURL);
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    expect(await dashboard.isLoaded()).toBe(true);

    const runCard = page.locator("[data-shape='home-run-card'], aside form");
    await expect(runCard.first()).toBeVisible({ timeout: 10000 });
    console.log('  ✅ Admin Dashboard verified with active RunCard control.');

    // Launch the pipeline run for this workspace via API with larger limit so it stays running for the stop test
    console.log('  • Launching active pipeline run on test workspace...');
    const runRes = await api.startPipelineRun(adminTokens.access, {
      workspace_id: testWorkspace.id,
      name: `Stop Journey Run - ${suffix}`,
      limit: 10,
      reprocess_existing: true,
    });
    launchedRunId = runRes.pipeline_run_id || runRes.id;
    console.log(`  🚀 Pipeline run started with ID: ${launchedRunId}`);

    // =========================================================================
    // Step 3: Navigate Directly to /runs/[id] & Verify Running State
    // =========================================================================
    console.log(`\n👑 Step 3: Navigating to Run Detail: /runs/${launchedRunId}...`);
    await page.goto(`/runs/${launchedRunId}`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator("h1:has-text('Run')").first()).toBeVisible({ timeout: 15000 });

    // =========================================================================
    // Step 4: Admin Stops the Running Pipeline via UI (StopRunButton)
    // =========================================================================
    console.log('\n👑 Step 4: Admin Stopping the Running Pipeline via UI...');
    const stopButton = page.locator("button:has-text('Stop'), button:has-text('Stoppen')").first();
    await expect(stopButton).toBeVisible({ timeout: 15000 });
    console.log('  • Stop button visible. Clicking to trigger confirmation modal...');
    await stopButton.click();

    // AlertDialog opens
    const modal = page.locator("[role='alertdialog']");
    await expect(modal).toBeVisible({ timeout: 5000 });
    console.log('  • Stop confirmation modal opened.');

    const confirmStopBtn = modal.locator("button:has-text('Stop'), button:has-text('Stoppen'), [data-slot='alert-dialog-action']").first();
    await confirmStopBtn.click();
    console.log('  • Confirmed Stop action.');

    // Wait for AlertDialog to close
    await expect(modal).toBeHidden({ timeout: 10000 });
    console.log('  ✅ Stop action successfully submitted.');

    // Wait for the status pill to change to Aborted
    const abortedPill = page.getByText(/^(Aborted|Abgebrochen)$/i).first();
    await expect(abortedPill).toBeVisible({ timeout: 20000 });
    console.log("  ✅ Run status successfully transitioned to 'Aborted'!");

    // =========================================================================
    // Step 5: Verify Admin Rerun Privilege on Aborted Run
    // =========================================================================
    console.log('\n👑 Step 5: Verifying Admin Rerun Privilege on Aborted Run...');
    const rerunButton = page.locator("button:has-text('Rerun'), button:has-text('Wiederholen')").first();
    await expect(rerunButton).toBeVisible({ timeout: 15000 });
    console.log('  ✅ Admin Rerun button verified on aborted pipeline run.');

    console.log('\n=================================================================');
    console.log('🎉 PIPELINE RUN ADMISSION & ADMIN-ONLY STOP JOURNEY COMPLETED!');
    console.log('=================================================================');
  });
});

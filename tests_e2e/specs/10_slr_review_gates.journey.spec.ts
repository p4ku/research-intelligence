import { test, expect } from '@playwright/test';
import {
  LoginPage,
  SidebarNav,
  AuditQueuePage,
  RunsPage,
  BriefingPage,
  SlrConsolePage,
  IncludedStudiesPage,
} from '../pages/index.js';
import { ApiHarness } from '../lib/api-harness.js';

test.describe('Journey 10: SLR Checkpoint Gates & Full User Lifecycle via React Interface', () => {
  // 8 minutes max for multi-stage research pipeline + human gates
  test.setTimeout(480_000);

  const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin';
  const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!';

  let api: ApiHarness;
  let adminToken: string;
  let workspaceId: string;
  let workspaceName: string;
  let pipelineRunId: string | null = null;

  test.beforeAll(async ({ baseURL }) => {
    const rootUrl = baseURL || 'https://annotate.soinventive.co.uk';
    api = new ApiHarness(rootUrl);

    console.log(`🔑 Authenticating test arbiter/admin via API against ${rootUrl}...`);
    const auth = await api.login(USERNAME, PASSWORD);
    adminToken = auth.access;

    const randomSuffix = Math.floor(10000000 + Math.random() * 90000000);
    workspaceName = `test_e2e_frontend_slr_${randomSuffix}`;

    console.log(`🧹 Pre-cleanup: Purging previous test workspaces...`);
    await api.cleanupOldTestWorkspaces(adminToken, 'test_e2e');

    console.log(`🏛️ Provisioning full SLR Workspace '${workspaceName}' with dual criteria, dynamic schemas & extractions...`);
    const ws = await api.createWorkspace(adminToken, {
      name: workspaceName,
      abstract_acceptance_criteria: 'Accept peer-reviewed research presenting computational algorithms, neural architectures, or deep learning evaluations.',
      abstract_rejection_criteria: 'Reject non-technical position papers and opinion articles.',
      abstract_screening_system_prompt: 'You are an expert AI Research Reviewer. Screen academic abstracts against criteria. Output valid JSON.',
      abstract_screening_user_prompt_template: '<DOCUMENT>\nTitle: {title}\nAbstract:\n{abstract}\n</DOCUMENT>\nCriteria:\n{acceptance_criteria}',
      abstract_screening_response_schema: {
        type: 'object',
        required: ['passed', 'reasoning', 'evidence_quotes', 'decision_category', 'fit_score'],
        properties: {
          passed: { type: 'boolean' },
          reasoning: { type: 'string' },
          evidence_quotes: { type: 'array', items: { type: 'string' } },
          decision_category: { type: 'string' },
          fit_score: { type: 'number', minimum: 0, maximum: 10 },
        },
      },
      abstract_screening_exit_metric: 'fit_score',
      full_text_acceptance_criteria: 'Accept papers with empirical evaluations, benchmarks, or mathematical derivations.',
      full_text_rejection_criteria: 'Reject papers with zero empirical metrics or absent methodology.',
      full_text_screening_system_prompt: 'Conduct a comprehensive full-text appraisal of the provided paper against criteria.',
      full_text_screening_user_prompt_template: '<DOCUMENT>\nTitle: {title}\nFull Text:\n{full_text}\n</DOCUMENT>\nCriteria:\n{acceptance_criteria}',
      full_text_screening_response_schema: {
        type: 'object',
        required: ['passed', 'reasoning', 'evidence_quotes', 'decision_category', 'novelty_score'],
        properties: {
          passed: { type: 'boolean' },
          reasoning: { type: 'string' },
          evidence_quotes: { type: 'array', items: { type: 'string' } },
          decision_category: { type: 'string' },
          novelty_score: { type: 'number', minimum: 0, maximum: 10 },
        },
      },
      full_text_screening_exit_metric: 'novelty_score',
      signal_score_code: 'fit = float(fit_score) if fit_score else 8.0\nnov = float(novelty_score) if novelty_score else 7.5\nreturn round(0.5 * fit + 0.5 * nov, 2)',
      narrative_report_system_prompt: 'Synthesize an Executive Briefing in Markdown.',
      narrative_report_prompt: 'Synthesize an Executive Briefing for workspace {workspace_name}.\nPapers:\n{papers}',
      screening_llm_model: process.env.E2E_LLM_MODEL || 'google/gemini-3.8-flash',
      llm_provider: process.env.E2E_LLM_PROVIDER || 'google',
      ocr_provider: 'pypdf',
      extraction_definitions: [
        {
          name: `Performance_Metrics_${randomSuffix}`,
          order: 1,
          primary_frontend_metric: 'accuracy_pct',
          secondary_frontend_metrics: ['latency_ms'],
          exit_metrics: ['accuracy_pct'],
          system_prompt: 'Extract model benchmark performance and accuracy percentage.',
          user_prompt_template: 'Paper: {title}\nExtract accuracy (0-100).',
          response_schema: {
            type: 'object',
            required: ['accuracy_pct', 'justification'],
            properties: {
              accuracy_pct: { type: 'number', minimum: 0, maximum: 100 },
              justification: { type: 'string' },
            },
          },
          postprocessing_code: 'acc = float(accuracy_pct) if "accuracy_pct" in locals() and accuracy_pct is not None else 90.0\nreturn {"accuracy_pct": acc}',
          llm_model: process.env.E2E_LLM_MODEL || 'google/gemini-3.8-flash',
          is_active: true,
        },
      ],
    });
    workspaceId = ws.id;

    console.log(`⚙️  Configuring SLR Policy Engine on workspace ${workspaceId}...`);
    await api.updateSLRConfig(adminToken, workspaceId, {
      checkpoint_gate_mode: 'two_stage_split',
      enable_extraction_gate: true,
      screening_quorum_size: 1,
      extraction_quorum_size: 1,
      sampling_mode: 'full_audit',
      abstract_sample_percentage: 100.0,
      full_text_sample_percentage: 100.0,
      extraction_sample_percentage: 100.0,
      negative_control_percentage: 0.0,
      enable_rob_assessment: true,
      rob_framework: 'auto_detect',
      tie_breaker_strategy: 'arbiter_ruling',
    });

    console.log(`🔍 Configuring Scraper with arXiv query (limit: 3 papers for fast, focused E2E lifecycle)...`);
    await api.createScraper(adminToken, {
      workspace: workspaceId,
      provider: 'arxiv',
      search_query: 'cat:cs.AI AND (all:"transformer" OR all:"neural")',
      limit: 3,
    });
  });

  test.afterAll(async () => {
    if (workspaceId && adminToken) {
      console.log(`🧹 Post-test Cleanup: Purging temporary workspace '${workspaceName}' (${workspaceId})...`);
      await api.deleteWorkspace(adminToken, workspaceId);
      console.log(`✅ Cleanup completed.`);
    }
  });

  test('Complete SLR Human-in-the-Loop Journey via React Interface: Login -> Run Launch -> Gate 1 Audit -> Gate 2 Audit -> Gate 3 Audit -> Synthesis -> Quality Console (/slr: PRISMA, RoB 2, Arbiter & Kappa)', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const sidebar = new SidebarNav(page);
    const auditQueue = new AuditQueuePage(page);
    const runsPage = new RunsPage(page);
    const briefingPage = new BriefingPage(page);
    const slrConsole = new SlrConsolePage(page);
    const includedStudies = new IncludedStudiesPage(page);

    // =========================================================================
    // Phase 1: Authentication via React Login Panel
    // =========================================================================
    console.log('🚀 Phase 1: Authentication via React Login Form');
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // If redirected to dashboard (e.g. from existing session cookies), sign out first
    if (page.url().includes('/dashboard')) {
      await sidebar.signOut();
      await page.goto('/');
      await page.waitForLoadState('networkidle');
    }

    await expect(loginPage.identifierInput).toBeVisible({ timeout: 10_000 });
    await loginPage.fillCredentials(USERNAME, PASSWORD);
    await loginPage.submit();

    // Verify arrival on Dashboard
    await page.waitForURL((url) => url.pathname.includes('/dashboard'), { timeout: 15_000 });
    console.log('  ✓ Authenticated successfully via React Login Panel.');

    // =========================================================================
    // Phase 2: Launching SLR Pipeline Run via React Dashboard
    // =========================================================================
    console.log(`🚀 Phase 2: Launching SLR Pipeline Run via React Dashboard for '${workspaceName}'`);
    
    // Select workspace in Domain dropdown if multiple exist
    const domainSelect = page.locator("select[name='workspace_id']").first();
    if (await domainSelect.isVisible({ timeout: 5000 })) {
      await domainSelect.selectOption(workspaceId);
      console.log(`  ✓ Selected workspace in domain dropdown.`);
    }

    // Click "SLR Review" briefing type tab
    const slrTypeTab = page.locator("button:has-text('SLR Review')").first();
    await expect(slrTypeTab).toBeVisible({ timeout: 5_000 });
    await slrTypeTab.click();
    console.log('  ✓ Selected "SLR Review" briefing type tab.');

    // Verify SLR Policy Active card appears in the React interface
    await expect(page.locator("text=/SLR Policy Active/i").first()).toBeVisible({ timeout: 5_000 });

    // Listen for the POST request to capture the pipeline run ID
    const runStartPromise = page.waitForResponse(
      (resp) => (resp.url().includes('/pipeline-runs') || resp.url().includes('/bff/pipeline-runs/start')) && resp.request().method() === 'POST',
      { timeout: 20_000 }
    ).catch(() => null);

    // Click "Start SLR Briefing" button
    const startButton = page.locator("button[type='submit']:has-text('Start SLR Briefing'), button[type='submit']:has-text('Start'), button[type='submit']").first();
    await expect(startButton).toBeVisible({ timeout: 5_000 });
    await startButton.click();
    console.log('  ✓ Clicked "Start SLR Briefing" button in React interface.');

    const runStartResp = await runStartPromise;
    if (runStartResp) {
      try {
        const respData = await runStartResp.json();
        pipelineRunId = respData.id || respData.run_id || respData.pipeline_run;
        console.log(`  ✓ Pipeline run triggered: ${pipelineRunId}`);
      } catch {
        // Response format varied
      }
    }

    // =========================================================================
    // Phase 3: Gate 1 (Abstract Screening Checkpoint in React UI)
    // =========================================================================
    console.log('\n⏸️  Phase 3: Monitoring & Auditing Gate 1 (Abstract Screening Checkpoint)...');
    await sidebar.navigateTo('audit-queue');
    const isG1CohortAvailable = await auditQueue.waitForWorkspaceCohort(workspaceName, { expectedGate: 'Abstract' });
    expect(isG1CohortAvailable).toBe(true);

    console.log('  ✓ Gate 1 Cohort appeared in Audit Queue table! Entering Split-Pane Review...');
    await auditQueue.clickReviewForWorkspace(workspaceName);

    let g1PaperIdx = 0;
    while (await auditQueue.isOnReviewPage()) {
      g1PaperIdx++;
      console.log(`  ✍️ Gate 1 Reviewing Paper #${g1PaperIdx} via React Split-Pane...`);

      // Verify split-pane elements are visible
      await expect(auditQueue.paperTitle).toBeVisible({ timeout: 5000 });
      await expect(auditQueue.leftViewerPane).toBeVisible({ timeout: 5000 });
      await expect(auditQueue.rightDecisionPane).toBeVisible({ timeout: 5000 });

      // Paper 1: Test human override (Override to Exclude with taxonomy reason & note)
      if (g1PaperIdx === 1) {
        console.log('    • Overriding AI decision: selecting Override Exclude with taxonomy reason & note...');
        await auditQueue.selectOverride({
          exclusionReason: 'Wrong Pathogen / Topic',
          note: 'Auditor human override: outside clinical scope.',
        });
      } else {
        // Subsequent papers: Agree with AI decision
        console.log('    • Agreeing with AI decision...');
        await auditQueue.selectAgreeWithAI();
      }

      const { isComplete } = await auditQueue.submitVerdict();

      if (isComplete) {
        console.log('  🎉 Gate 1 Completion Modal reached: Audit Checkpoint Complete!');
        await auditQueue.returnToQueue();
        break;
      }
    }
    console.log('  ✅ Gate 1 Abstract Screening Checkpoint completed through React UI!');

    // =========================================================================
    // Phase 4: Gate 2 (Full-Text Screening Checkpoint in React UI)
    // =========================================================================
    console.log('\n⏸️  Phase 4: Monitoring & Auditing Gate 2 (Full-Text Screening Checkpoint)...');
    if (new URL(page.url()).pathname !== '/audit-queue') {
      await sidebar.navigateTo('audit-queue');
    }
    const isG2CohortAvailable = await auditQueue.waitForWorkspaceCohort(workspaceName, { expectedGate: 'Full-text' });
    expect(isG2CohortAvailable).toBe(true);

    console.log('  ✓ Gate 2 Full-Text Cohort appeared in Audit Queue! Entering Review via whole-row click...');
    await auditQueue.clickTableRowForWorkspace(workspaceName);

    let g2PaperIdx = 0;
    while (await auditQueue.isOnReviewPage()) {
      g2PaperIdx++;
      console.log(`  ✍️ Gate 2 Reviewing Full-Text Paper #${g2PaperIdx} via React Split-Pane...`);

      await expect(auditQueue.paperTitle).toBeVisible({ timeout: 5000 });
      await auditQueue.selectAgreeWithAI();
      const { isComplete } = await auditQueue.submitVerdict();

      if (isComplete) {
        console.log('  🎉 Gate 2 Completion Modal reached: Full-Text Checkpoint Complete!');
        await auditQueue.returnToQueue();
        break;
      }
    }
    console.log('  ✅ Gate 2 Full-Text Screening Checkpoint completed through React UI!');

    // =========================================================================
    // Phase 5: Gate 3 (Parameter Extraction Audit Gate in React UI)
    // =========================================================================
    console.log('\n⏸️  Phase 5: Monitoring & Auditing Gate 3 (Extraction Audit Gate)...');
    if (new URL(page.url()).pathname !== '/audit-queue') {
      await sidebar.navigateTo('audit-queue');
    }
    const isG3CohortAvailable = await auditQueue.waitForWorkspaceCohort(workspaceName, { expectedGate: 'Parameter' });
    expect(isG3CohortAvailable).toBe(true);

    console.log('  ✓ Gate 3 Extraction Cohort appeared in Audit Queue! Entering Review...');
    await auditQueue.clickReviewForWorkspace(workspaceName);

    let g3PaperIdx = 0;
    while (await auditQueue.isOnReviewPage()) {
      g3PaperIdx++;
      console.log(`  ✍️ Gate 3 Auditing Extractions for Paper #${g3PaperIdx}...`);

      const isExt = await auditQueue.isExtractionStage();
      if (isExt) {
        console.log('    • AI Extraction Audit Panel active: verifying and modifying parameter values...');
        await auditQueue.auditExtraction({
          modifyFirst: g3PaperIdx === 1,
          note: 'Audited parameter extraction: verified against empirical figures.',
        });
      } else {
        await auditQueue.selectAgreeWithAI();
      }

      const { isComplete } = await auditQueue.submitVerdict();

      if (isComplete) {
        console.log('  🎉 Gate 3 Completion Modal reached: Extraction Audit Complete!');
        // Click "Monitor Pipeline Run →" in the completion modal
        await auditQueue.monitorPipelineRun();
        break;
      }
    }
    console.log('  ✅ Gate 3 Extraction Audit completed through React UI!');

    // =========================================================================
    // Phase 6: Final Pipeline Completion & Results in React Interface
    // =========================================================================
    console.log('\n🏁 Phase 6: Verifying Pipeline Completion & Results in React Interface...');
    if (!page.url().includes('/runs')) {
      await sidebar.navigateTo('runs');
    }
    expect(await runsPage.isLoaded()).toBe(true);

    // Wait for pipeline run status to become Completed
    console.log('  Waiting for pipeline run status to become Completed in React UI...');
    let isRunFinished = false;
    const tStart = Date.now();
    while (Date.now() - tStart < 180_000) {
      const pageText = (await page.locator("main, tbody").first().textContent().catch(() => '')) || '';
      if (
        pageText.includes('Completed') ||
        pageText.includes('completed') ||
        pageText.includes('Abgeschlossen')
      ) {
        isRunFinished = true;
        break;
      }
      await page.waitForTimeout(4000);
      await page.reload();
      await page.waitForLoadState('networkidle');
    }
    expect(isRunFinished).toBe(true);
    console.log('  ✓ Pipeline Run confirmed Completed in React UI!');

    // =========================================================================
    // Phase 7: Verification of Unified SLR Console (/slr)
    // (PRISMA 2020 Flow, RoB 2 Traffic Light Matrix, Agreement KPIs & Arbiter)
    // =========================================================================
    console.log('\n🔬 Phase 7: Navigating to Unified SLR Console (/slr)...');
    await sidebar.navigateTo('slr');
    expect(await slrConsole.isLoaded()).toBe(true);
    console.log('  ✓ SLR Review & Quality Console loaded successfully.');

    // 1. Wskaźniki Zgodności (Cohen's Kappa & Kalibracja AI)
    console.log('  Verifying Agreement & AI Calibration KPI Cards...');
    await slrConsole.verifyAgreementKpis();
    console.log('  ✓ All 4 Statistical Agreement KPI cards verified in React UI!');

    // 2. Diagram PRISMA 2020 Flow
    console.log('  Verifying PRISMA 2020 Flow Diagram...');
    await slrConsole.verifyPrismaFlow();
    console.log('  ✓ PRISMA 2020 Statement Flow Diagram verified!');

    // 3. Senior Arbiter Adjudication Console
    console.log('  Verifying Senior Arbiter Console...');
    await slrConsole.verifyArbiterConsole();
    console.log('  ✓ Senior Arbiter Console verified in React UI!');

    // 4. Risk of Bias Traffic Light Matrix & Drawer
    console.log('  Verifying Cochrane Risk of Bias (RoB 2) Matrix & Grounding Drawer...');
    await slrConsole.verifyRobMatrixAndDrawer();
    console.log('  ✓ Cochrane Risk of Bias Traffic Light Matrix & Drawer verified!');

    // 5. PRISMA Stage 4 Included Studies Catalogue (/slr/studies)
    console.log('  Navigating to PRISMA Stage 4 Included Studies Catalogue (/slr/studies)...');
    await slrConsole.navigateToIncludedStudies();
    expect(await includedStudies.isLoaded()).toBe(true);
    console.log('  ✓ Included Studies Catalogue loaded successfully on /slr/studies.');

    await includedStudies.verifySummaryCards();
    await includedStudies.testSearchAndFilters('Transformer');
    await includedStudies.testGroundingEvidenceDrawer();

    // Return to /slr via breadcrumb
    console.log('  Returning to /slr console via breadcrumbs...');
    await includedStudies.clickBreadcrumbBack();
    expect(await slrConsole.isLoaded()).toBe(true);
    console.log('  ✓ Successfully returned to /slr console via breadcrumbs.');

    console.log('=================================================================');
    console.log('🎉 FULL SLR USER JOURNEY VIA REACT INTERFACE PASSED SUCCESSFULLY!');
    console.log('=================================================================');
  });
});

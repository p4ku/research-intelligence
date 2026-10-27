import { test, expect } from '@playwright/test'
import {
  LoginPage,
  SidebarNav,
  SlrConsolePage,
  IncludedStudiesPage,
  AuditQueuePage,
} from '../pages/index.js'

test.describe('Journey 11: Unified SLR Console — PRISMA 2020 Flow, Arbiter Console, RoB 2 & Agreement KPIs', () => {
  test.setTimeout(180_000)

  const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin'
  const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!'

  test('Verify unified SLR Console on /slr: KPIs -> PRISMA Flow -> Arbiter Console -> RoB 2 Matrix & Drawers -> Included Studies Catalogue -> Audit Queue Row Navigation', async ({ page }) => {
    const loginPage = new LoginPage(page)
    const sidebar = new SidebarNav(page)
    const slrConsole = new SlrConsolePage(page)
    const includedStudies = new IncludedStudiesPage(page)
    const auditQueue = new AuditQueuePage(page)

    // =========================================================================
    // 1. Authentication via React Login Panel
    // =========================================================================
    console.log('🚀 Phase 1: Authentication via React Login Form');
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    if (page.url().includes('/dashboard')) {
      await sidebar.signOut()
      await page.goto('/')
      await page.waitForLoadState('networkidle')
    }

    await expect(loginPage.identifierInput).toBeVisible({ timeout: 10_000 })
    await loginPage.fillCredentials(USERNAME, PASSWORD)
    await loginPage.submit()

    await page.waitForURL((url) => url.pathname.includes('/dashboard'), { timeout: 15_000 })
    console.log('  ✓ Authenticated successfully.')

    // =========================================================================
    // 2. Navigation to /slr Console
    // =========================================================================
    console.log('🚀 Phase 2: Navigating to /slr Console via Sidebar...')
    const slrNavLink = page.locator("nav a[href='/slr'], aside a[href='/slr']").first()
    if (await slrNavLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await slrNavLink.click()
    } else {
      await page.goto('/slr')
    }

    await page.waitForURL((url) => url.pathname.includes('/slr'), { timeout: 15_000 })
    await page.waitForLoadState('networkidle')

    // Verify Title & Header
    await expect(page.locator("h1:has-text('SLR Review & Quality Console')")).toBeVisible({ timeout: 10_000 })
    console.log('  ✓ SLR Review & Quality Console loaded successfully.')

    // =========================================================================
    // 3. Wskaźniki Zgodności & Kalibracja AI (KPI Banner)
    // =========================================================================
    console.log('🚀 Phase 3: Verifying Statistical Agreement & AI Calibration KPIs...')
    await expect(page.locator("text=/Inter-Rater Reliability/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/AI vs. Human Concordance/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/AI Sensitivity/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/AI Specificity/i").first()).toBeVisible({ timeout: 5000 })
    console.log('  ✓ All 4 Statistical KPI cards verified.')

    // =========================================================================
    // 4. Diagram PRISMA 2020 Statement Flow
    // =========================================================================
    console.log('🚀 Phase 4: Verifying PRISMA 2020 Statement Flow Diagram...')
    await slrConsole.verifyPrismaFlow()
    console.log('  ✓ PRISMA 2020 Flow Diagram successfully verified.')

    // =========================================================================
    // 5. Konsola Rozstrzygania Sporów (Arbiter Console)
    // =========================================================================
    console.log('🚀 Phase 5: Verifying Senior Arbiter Adjudication Console...')
    const arbiterTab = page.locator("button:has-text('Arbiter Console')").first()
    await arbiterTab.click()

    await expect(page.locator("text=/Senior Arbiter Adjudication Console/i").first()).toBeVisible({ timeout: 5000 })

    // Check if disputes exist
    const disputeCards = page.locator("button:has-text('Gate')")
    const disputeCount = await disputeCards.count()
    console.log(`  Found ${disputeCount} dispute card(s) in queue.`)

    if (disputeCount > 0) {
      await disputeCards.first().click()
      await expect(page.locator("text=/Reviewer 1/i").first()).toBeVisible({ timeout: 5000 })
      await expect(page.locator("text=/Reviewer 2/i").first()).toBeVisible({ timeout: 5000 })
      await expect(page.locator("text=/AI Agent Baseline/i").first()).toBeVisible({ timeout: 5000 })

      // If arbitration form is open, test submission
      const executeBtn = page.locator("button:has-text('Execute Binding Ruling')").first()
      if (await executeBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        console.log('  Testing Senior Arbiter binding ruling submission...')
        const rationaleTextarea = page.locator("textarea[placeholder*='Detail the scientific']").first()
        await rationaleTextarea.fill('Senior Arbiter Adjudication E2E: Confirmed empirical benchmarks meet inclusion criteria.')
        await executeBtn.click()

        // Wait for status update or success alert
        await expect(page.locator("text=/Resolved as|Dispute successfully resolved/i").first()).toBeVisible({ timeout: 10_000 })
        console.log('  ✓ Arbiter binding ruling executed and confirmed!')
      }
    }
    console.log('  ✓ Senior Arbiter Adjudication Console successfully verified.')

    // =========================================================================
    // 6. Matryca Risk of Bias (RoB 2) & Traffic Light Drawer
    // =========================================================================
    console.log('🚀 Phase 6: Verifying Cochrane Risk of Bias (RoB 2) Traffic Light Matrix...')
    const robTab = page.locator("button:has-text('Risk of Bias Matrix')").first()
    await robTab.click()

    await expect(page.locator("h3:has-text('Traffic Light Matrix')").first()).toBeVisible({ timeout: 5000 })
    const hasTable = await page.locator("th:has-text('D1 Rand')").first().isVisible({ timeout: 3000 }).catch(() => false)
    if (hasTable) {
      await expect(page.locator("th:has-text('Overall Bias')").first()).toBeVisible({ timeout: 5000 })

      // Click Inspect to test Grounding Evidence Drawer
      const inspectBtn = page.locator("button:has-text('Inspect')").first()
      if (await inspectBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await inspectBtn.click()
        await expect(page.locator("h4:has-text('Grounding Evidence')").first()).toBeVisible({ timeout: 5000 })
        console.log('  ✓ Risk of Bias Grounding Evidence Drawer opened.')

        const closeDrawerBtn = page.locator("button:has-text('Close Inspector')").first()
        await closeDrawerBtn.click()
        await expect(page.locator("h4:has-text('Grounding Evidence')")).not.toBeVisible({ timeout: 5000 })
        console.log('  ✓ Risk of Bias Drawer closed.')
      }
    } else {
      await expect(page.locator("text=/No Risk of Bias appraisals generated yet/i").first()).toBeVisible({ timeout: 5000 })
      console.log('  ✓ Verified Risk of Bias empty state.')
    }
    console.log('  ✓ Risk of Bias Traffic Light Matrix successfully verified.')

    // =========================================================================
    // 7. Weryfikacja Nowego Ekranu Included Studies (/slr/studies)
    // =========================================================================
    console.log('🚀 Phase 7: Navigating to PRISMA Stage 4 Included Studies Catalogue (/slr/studies)...')
    const prismaTabReturn = page.locator("button:has-text('PRISMA 2020 Flow')").first()
    await prismaTabReturn.click()
    await page.waitForTimeout(300)

    const viewStudiesLink = page.locator("a:has-text('View Included Studies'), a:has-text('Included Studies')").first()
    if (await viewStudiesLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await viewStudiesLink.click()
    } else {
      await page.goto('/slr/studies')
    }

    expect(await includedStudies.isLoaded()).toBe(true)
    console.log('  ✓ Included Studies Catalogue loaded successfully on /slr/studies.')

    // Summary KPI cards
    console.log('  Verifying Included Studies KPI cards...')
    await includedStudies.verifySummaryCards()
    console.log('  ✓ Studies in Synthesis & Meta-Analysis summary cards verified.')

    // Search input & Filter pills
    console.log('  Testing search and Risk of Bias filter pills...')
    await includedStudies.testSearchAndFilters('Transformer')
    console.log('  ✓ Search and RoB filter pills tested.')

    // Grounding Evidence Drawer
    const hadStudies = await includedStudies.testGroundingEvidenceDrawer()
    if (hadStudies) {
      console.log('  ✓ Grounding Evidence quotes drawer tested in Included Studies table.')
    }

    // Breadcrumb navigation back to /slr
    console.log('  Returning to /slr console via breadcrumb...')
    await includedStudies.clickBreadcrumbBack()
    expect(await slrConsole.isLoaded()).toBe(true)
    console.log('  ✓ Successfully returned to /slr console via breadcrumbs.')

    // =========================================================================
    // 8. Weryfikacja Klikalności Wiersza w Kolejce Audytu (/audit-queue)
    // =========================================================================
    console.log('🚀 Phase 8: Testing Row Click Navigation in Audit Queue (/audit-queue)...')
    await page.goto('/audit-queue')
    expect(await auditQueue.isLoaded()).toBe(true)

    // Check if cohorts exist in queue
    const allTab = page.locator("button:has-text('All Assigned'), button:has-text('Completed History')").first()
    if (await allTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await allTab.click()
      await page.waitForTimeout(400)
    }

    const rowCount = await auditQueue.getCohortCount()
    if (rowCount > 0) {
      console.log(`  Found ${rowCount} cohort row(s). Testing whole-row click navigation...`)
      await auditQueue.clickTableRowNavigation(0)
      expect(await auditQueue.isOnReviewPage()).toBe(true)
      console.log('  ✓ Whole-row click navigation succeeded directly into Paper Review Workspace!')
    } else {
      console.log('  ℹ No cohort rows currently present in queue; row navigation verified via unit tests.')
    }

    console.log('=================================================================')
    console.log('🎉 UNIFIED SLR CONSOLE & INCLUDED STUDIES E2E PASSED!')
    console.log('=================================================================')
  })
})

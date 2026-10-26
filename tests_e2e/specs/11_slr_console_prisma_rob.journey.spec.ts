import { test, expect } from '@playwright/test'
import { LoginPage, SidebarNav } from '../pages/index.js'

test.describe('Journey 11: Unified SLR Console — PRISMA 2020 Flow, Arbiter Console, RoB 2 & Agreement KPIs', () => {
  test.setTimeout(120_000)

  const USERNAME = process.env.ADMIN_USERNAME || process.env.CONTRACT_USER || 'admin'
  const PASSWORD = process.env.ADMIN_PASSWORD || process.env.CONTRACT_PASSWORD || 'schwarz123!'

  test('Verify unified SLR Console on /slr: KPIs -> PRISMA Flow -> Arbiter Console -> RoB 2 Matrix & Drawers', async ({ page }) => {
    const loginPage = new LoginPage(page)
    const sidebar = new SidebarNav(page)

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
    const prismaTab = page.locator("button:has-text('PRISMA 2020 Flow')").first()
    await prismaTab.click()

    await expect(page.locator("text=/PRISMA 2020 Statement Flow Diagram/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/1.*Identification/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/2.*Screening/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/3.*Eligibility/i").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator("text=/4.*Included Studies/i").first()).toBeVisible({ timeout: 5000 })

    // Test reason toggle button if visible
    const toggleButton = page.locator("button:has-text('Hide reason breakdown'), button:has-text('Show reason breakdown')").first()
    if (await toggleButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await toggleButton.click()
      console.log('  ✓ Toggled PRISMA exclusion reason breakdown.')
    }
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
    await expect(page.locator("th:has-text('D1 Rand')").first()).toBeVisible({ timeout: 5000 })
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
    console.log('  ✓ Risk of Bias Traffic Light Matrix successfully verified.')

    console.log('=================================================================')
    console.log('🎉 UNIFIED SLR CONSOLE E2E VERIFICATION COMPLETED SUCCESSFULLY!')
    console.log('=================================================================')
  })
})

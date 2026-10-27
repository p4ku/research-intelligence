import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class IncludedStudiesPage extends BasePage {
  readonly pageTitle: Locator;
  readonly breadcrumbBackLink: Locator;
  readonly runSelector: Locator;
  readonly kpiSynthesis: Locator;
  readonly kpiMetaAnalysis: Locator;
  readonly kpiLowRisk: Locator;
  readonly searchInput: Locator;
  readonly filterAll: Locator;
  readonly filterLowRisk: Locator;
  readonly filterSomeConcerns: Locator;
  readonly filterHighRisk: Locator;
  readonly exportCsvButton: Locator;
  readonly tableRows: Locator;
  readonly inspectButtons: Locator;
  readonly drawerHeading: Locator;
  readonly closeDrawerButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Included Studies')").first();
    this.breadcrumbBackLink = page.locator("a:has-text('SLR Review & Quality Console')").first();
    this.runSelector = page.locator("select").first();
    this.kpiSynthesis = page.locator("text=/Studies in Synthesis/i").first();
    this.kpiMetaAnalysis = page.locator("text=/Quantitative Meta-Analysis/i").first();
    this.kpiLowRisk = page.locator("text=/Low Risk of Bias/i").first();
    this.searchInput = page.locator("input[placeholder*='Search included studies']").first();
    this.filterAll = page.locator("button:has-text('All Admitted')").first();
    this.filterLowRisk = page.locator("button:has-text('Low Risk')").first();
    this.filterSomeConcerns = page.locator("button:has-text('Some Concerns')").first();
    this.filterHighRisk = page.locator("button:has-text('High Risk')").first();
    this.exportCsvButton = page.locator("button:has-text('Export Studies')").first();
    this.tableRows = page.locator("tbody tr");
    this.inspectButtons = page.locator("tbody tr button:has-text('Inspect')");
    this.drawerHeading = page.locator("h4:has-text('Grounding Evidence Quotes')").first();
    this.closeDrawerButton = page.locator("button:has-text('Close Drawer')").first();
  }

  async isLoaded(): Promise<boolean> {
    try {
      await this.page.waitForURL((url) => url.pathname.includes('/slr/studies'), { timeout: 15_000 });
      await expect(this.pageTitle).toBeVisible({ timeout: 10_000 });
      return true;
    } catch {
      return false;
    }
  }

  async verifySummaryCards(): Promise<void> {
    await expect(this.kpiSynthesis).toBeVisible({ timeout: 5000 });
    await expect(this.kpiMetaAnalysis).toBeVisible({ timeout: 5000 });
    await expect(this.kpiLowRisk).toBeVisible({ timeout: 5000 });
  }

  async testSearchAndFilters(query: string = 'Clinical'): Promise<void> {
    if (await this.searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await this.searchInput.fill(query);
      await this.page.waitForTimeout(300);
      await this.searchInput.clear();
      await this.page.waitForTimeout(200);
    }

    if (await this.filterLowRisk.isVisible({ timeout: 3000 }).catch(() => false)) {
      await this.filterLowRisk.click();
      await this.page.waitForTimeout(200);
      await this.filterAll.click();
      await this.page.waitForTimeout(200);
    }
  }

  async testGroundingEvidenceDrawer(): Promise<boolean> {
    const inspectCount = await this.inspectButtons.count();
    if (inspectCount > 0) {
      await this.inspectButtons.first().click();
      await expect(this.drawerHeading).toBeVisible({ timeout: 5000 });

      await this.closeDrawerButton.click();
      await expect(this.drawerHeading).not.toBeVisible({ timeout: 5000 });
      return true;
    }
    return false;
  }

  async clickBreadcrumbBack(): Promise<void> {
    await expect(this.breadcrumbBackLink).toBeVisible({ timeout: 5000 });
    await this.breadcrumbBackLink.click();
    await this.page.waitForURL((url) => url.pathname === '/slr' || (url.pathname.includes('/slr') && !url.pathname.includes('/studies')), { timeout: 15_000 });
  }
}

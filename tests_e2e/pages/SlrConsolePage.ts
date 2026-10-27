import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class SlrConsolePage extends BasePage {
  readonly pageTitle: Locator;
  readonly runSelector: Locator;
  readonly kpiInterRater: Locator;
  readonly kpiAiConcordance: Locator;
  readonly kpiSensitivity: Locator;
  readonly kpiSpecificity: Locator;
  readonly tabPrisma: Locator;
  readonly tabArbiter: Locator;
  readonly tabRob: Locator;
  readonly prismaHeading: Locator;
  readonly prismaStage1: Locator;
  readonly prismaStage2: Locator;
  readonly prismaStage3: Locator;
  readonly prismaStage4: Locator;
  readonly arbiterHeading: Locator;
  readonly robHeading: Locator;
  readonly viewIncludedStudiesAction: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('SLR Review & Quality Console')").first();
    this.runSelector = page.locator("select").first();
    this.kpiInterRater = page.locator("text=/Inter-Rater Reliability/i").first();
    this.kpiAiConcordance = page.locator("text=/AI vs. Human Concordance/i").first();
    this.kpiSensitivity = page.locator("text=/AI Sensitivity/i").first();
    this.kpiSpecificity = page.locator("text=/AI Specificity/i").first();

    this.tabPrisma = page.locator("button:has-text('PRISMA 2020 Flow')").first();
    this.tabArbiter = page.locator("button:has-text('Arbiter Console')").first();
    this.tabRob = page.locator("button:has-text('Risk of Bias Matrix')").first();

    this.prismaHeading = page.locator("text=/PRISMA 2020 Statement Flow Diagram/i").first();
    this.prismaStage1 = page.locator("text=/1.*Identification/i").first();
    this.prismaStage2 = page.locator("text=/2.*Screening/i").first();
    this.prismaStage3 = page.locator("text=/3.*Eligibility/i").first();
    this.prismaStage4 = page.locator("text=/4.*Included Studies/i").first();

    this.arbiterHeading = page.locator("text=/Senior Arbiter Adjudication Console/i").first();
    this.robHeading = page.locator("h3:has-text('Traffic Light Matrix')").first();
    this.viewIncludedStudiesAction = page.locator("a:has-text('View Included Studies'), a:has-text('Included Studies')").first();
  }

  async isLoaded(): Promise<boolean> {
    try {
      await expect(this.pageTitle).toBeVisible({ timeout: 10_000 });
      return true;
    } catch {
      return false;
    }
  }

  async selectRun(runId: string): Promise<void> {
    if (await this.runSelector.isVisible({ timeout: 3000 }).catch(() => false)) {
      await this.runSelector.selectOption(runId);
      await this.page.waitForLoadState('networkidle');
    }
  }

  async verifyAgreementKpis(): Promise<void> {
    await expect(this.kpiInterRater).toBeVisible({ timeout: 5000 });
    await expect(this.kpiAiConcordance).toBeVisible({ timeout: 5000 });
    await expect(this.kpiSensitivity).toBeVisible({ timeout: 5000 });
    await expect(this.kpiSpecificity).toBeVisible({ timeout: 5000 });
  }

  async selectTab(tab: 'prisma' | 'arbiter' | 'rob'): Promise<void> {
    if (tab === 'prisma') await this.tabPrisma.click();
    else if (tab === 'arbiter') await this.tabArbiter.click();
    else if (tab === 'rob') await this.tabRob.click();
    await this.page.waitForTimeout(300);
  }

  async verifyPrismaFlow(): Promise<void> {
    await this.selectTab('prisma');
    const hasDiagram = await this.prismaHeading.isVisible({ timeout: 5000 }).catch(() => false);
    if (hasDiagram) {
      await expect(this.prismaStage1).toBeVisible({ timeout: 5000 });
      await expect(this.prismaStage2).toBeVisible({ timeout: 5000 });
      await expect(this.prismaStage3).toBeVisible({ timeout: 5000 });
      await expect(this.prismaStage4).toBeVisible({ timeout: 5000 });

      const toggle = this.page.locator("button:has-text('Hide reason breakdown'), button:has-text('Show reason breakdown')").first();
      if (await toggle.isVisible({ timeout: 2000 }).catch(() => false)) {
        await toggle.click();
      }
    } else {
      await expect(this.page.locator("text=/No PRISMA flow metrics available/i").first()).toBeVisible({ timeout: 5000 });
    }
  }

  async verifyArbiterConsole(): Promise<void> {
    await this.selectTab('arbiter');
    await expect(this.arbiterHeading).toBeVisible({ timeout: 5000 });
  }

  async verifyRobMatrixAndDrawer(): Promise<void> {
    await this.selectTab('rob');
    await expect(this.robHeading).toBeVisible({ timeout: 5000 });
    const hasTable = await this.page.locator("th:has-text('D1 Rand')").first().isVisible({ timeout: 3000 }).catch(() => false);
    if (hasTable) {
      await expect(this.page.locator("th:has-text('Overall Bias')").first()).toBeVisible({ timeout: 5000 });

      const inspectBtn = this.page.locator("button:has-text('Inspect')").first();
      if (await inspectBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await inspectBtn.click();
        await expect(this.page.locator("h4:has-text('Grounding Evidence')").first()).toBeVisible({ timeout: 5000 });

        const closeBtn = this.page.locator("button:has-text('Close Inspector')").first();
        await closeBtn.click();
        await expect(this.page.locator("h4:has-text('Grounding Evidence')")).not.toBeVisible({ timeout: 5000 });
      }
    } else {
      await expect(this.page.locator("text=/No Risk of Bias appraisals generated yet/i").first()).toBeVisible({ timeout: 5000 });
    }
  }

  async navigateToIncludedStudies(): Promise<void> {
    await this.selectTab('prisma');
    await expect(this.viewIncludedStudiesAction).toBeVisible({ timeout: 10_000 });
    await this.viewIncludedStudiesAction.click();
    await this.page.waitForURL((url) => url.pathname.includes('/slr/studies'), { timeout: 15_000 });
    await this.waitForNetworkIdle();
  }
}

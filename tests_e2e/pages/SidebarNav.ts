import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class SidebarNav extends BasePage {
  readonly navDashboard: Locator;
  readonly navBriefing: Locator;
  readonly navPapers: Locator;
  readonly navScoring: Locator;
  readonly navAsk: Locator;
  readonly userMenuButton: Locator;
  readonly userNameLabel: Locator;
  readonly menuSettingsItem: Locator;
  readonly menuLanguageToggle: Locator;
  readonly menuSignOutButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.navDashboard = page.locator("a[href='/dashboard'], nav a:has-text('Today'), nav a:has-text('Heute')").first();
    this.navBriefing = page.locator("a[href='/briefing'], nav a:has-text('Briefings')").first();
    this.navPapers = page.locator("a[href='/papers'], nav a:has-text('Papers')").first();
    this.navScoring = page.locator("a[href='/scoring'], nav a:has-text('Scoring')").first();
    this.navAsk = page.locator("a[href='/ask'], nav a:has-text('Ask'), nav a:has-text('Fragen')").first();

    this.userMenuButton = page.locator("button[aria-haspopup='menu']:visible, aside button:visible, nav button:visible").last();
    this.userNameLabel = page.locator("span.truncate:visible, button:has([data-slot='avatar']) span").first();
    this.menuSettingsItem = page.locator("[role='menu'] a[href='/settings'], [role='menuitem']:has-text('Settings'), [role='menuitem']:has-text('Einstellungen')").first();
    this.menuLanguageToggle = page.locator("[role='menu'] [role='menuitem']:has-text('Deutsch'), [role='menu'] [role='menuitem']:has-text('English')").first();
    this.menuSignOutButton = page.locator("[role='menu'] [role='menuitem']:has-text('Sign out'), [role='menu'] [role='menuitem']:has-text('Abmelden')").first();
  }

  async navigateTo(target: string): Promise<void> {
    const targetLower = target.toLowerCase().trim();
    if (['dashboard', 'today', 'heute', '/dashboard'].includes(targetLower)) {
      await this.navDashboard.click();
      await this.waitForURLContains('/dashboard');
    } else if (['briefing', 'briefings', '/briefing'].includes(targetLower)) {
      await this.navBriefing.click();
      await this.waitForURLContains('/briefing');
    } else if (['papers', 'paper', '/papers'].includes(targetLower)) {
      await this.navPapers.click();
      await this.waitForURLContains('/papers');
    } else if (['scoring', '/scoring'].includes(targetLower)) {
      await this.navScoring.click();
      await this.waitForURLContains('/scoring');
    } else if (['ask', 'chat', '/ask'].includes(targetLower)) {
      await this.navAsk.click();
      await this.waitForURLContains('/ask');
    } else if (['settings', '/settings'].includes(targetLower)) {
      await this.goto('/settings');
    } else {
      await this.goto(target);
    }
    await this.waitForNetworkIdle();
  }

  async openUserMenu(): Promise<void> {
    const menu = this.page.locator("[role='menu']");
    if (!(await menu.isVisible())) {
      await this.userMenuButton.scrollIntoViewIfNeeded();
      await this.userMenuButton.click({ force: true });
      await this.page.waitForSelector("[role='menu']", { timeout: 5000 });
    }
  }

  async toggleLanguage(): Promise<void> {
    try {
      await this.openUserMenu();
      await this.menuLanguageToggle.click({ timeout: 3000 });
    } catch {
      // Ignored
    }
    await this.waitForNetworkIdle();
  }

  async signOut(): Promise<void> {
    try {
      await this.openUserMenu();
      await this.menuSignOutButton.click({ timeout: 3000 });
      await this.page.waitForURL((url) => {
        const u = url.toString();
        return u.endsWith('/') || u.includes('login') || u.includes('auth');
      }, { timeout: 10000 });
    } catch {
      // Fallback direct session drop
      await this.page.evaluate(() => fetch('/auth/logout', { method: 'POST' }));
      await this.goto('/');
    }
    await this.waitForNetworkIdle();
  }

  async getUserName(): Promise<string | null> {
    try {
      if (await this.userNameLabel.isVisible({ timeout: 3000 })) {
        return (await this.userNameLabel.textContent())?.trim() ?? null;
      }
    } catch {
      // Ignored
    }
    return null;
  }
}

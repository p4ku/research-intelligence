import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';
import { LoginPage } from './LoginPage.js';

export class SidebarNav extends BasePage {
  readonly navDashboard: Locator;
  readonly navBriefing: Locator;
  readonly navPapers: Locator;
  readonly navTuning: Locator;
  readonly navAsk: Locator;
  readonly navRuns: Locator;
  readonly navAuditQueue: Locator;
  readonly userMenuButton: Locator;
  readonly userNameLabel: Locator;
  readonly menuSettingsItem: Locator;
  readonly menuLanguageToggle: Locator;
  readonly menuSignOutButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    // The German nav row is "Start" (it stopped being "Heute" on 9 Sep 2026).
    this.navDashboard = page.locator("a[href='/dashboard'], nav a:has-text('Home'), nav a:has-text('Start'), aside a[href='/dashboard']").first();
    this.navBriefing = page.locator("a[href='/briefing'], nav a:has-text('Briefings'), aside a[href='/briefing']").first();
    this.navPapers = page.locator("a[href='/papers'], nav a:has-text('Papers'), aside a[href='/papers']").first();
    this.navTuning = page.locator("a[href='/tuning'], nav a:has-text('Tuning'), aside a[href='/tuning']").first();
    this.navAsk = page.locator("a[href='/ask'], nav a:has-text('Ask'), nav a:has-text('Fragen'), aside a[href='/ask']").first();
    this.navRuns = page.locator("a[href='/runs'], nav a:has-text('Runs'), aside a[href='/runs']").first();
    this.navAuditQueue = page.locator("a[href='/audit-queue'], nav a:has-text('Audit Queue'), nav a:has-text('Prüfwarteschlange'), aside a[href='/audit-queue']").first();

    this.userMenuButton = page.locator(
      "aside footer button, aside footer [role='button'], aside footer [data-slot='item'], button:has([data-slot='avatar']), header button:has([data-slot='avatar'])"
    ).first();
    this.userNameLabel = page.locator("aside footer span.truncate, span.truncate:visible, button:has([data-slot='avatar']) span").first();
    this.menuSettingsItem = page.locator("[role='menu'] a[href='/settings'], [role='menuitem']:has-text('Settings'), [role='menuitem']:has-text('Einstellungen')").first();
    this.menuLanguageToggle = page.locator("[role='menu'] [role='menuitem']:has-text('Deutsch'), [role='menu'] [role='menuitem']:has-text('English')").first();
    this.menuSignOutButton = page.locator("[role='menu'] [role='menuitem']:has-text('Sign out'), [role='menu'] [role='menuitem']:has-text('Abmelden')").first();
  }

  async navigateTo(target: string): Promise<void> {
    const targetLower = target.toLowerCase().trim();
    const currentUrl = this.page.url();

    if (['dashboard', 'home', 'today', 'heute', 'start', '/dashboard'].includes(targetLower)) {
      if (!currentUrl.includes('/dashboard')) {
        try {
          if (await this.navDashboard.isVisible({ timeout: 3000 })) {
            await this.navDashboard.click();
            await this.waitForURLContains('/dashboard');
          } else {
            await this.goto('/dashboard');
          }
        } catch {
          await this.goto('/dashboard');
        }
      }
    } else if (['briefing', 'briefings', '/briefing'].includes(targetLower)) {
      if (!currentUrl.includes('/briefing')) {
        try {
          if (await this.navBriefing.isVisible({ timeout: 3000 })) {
            await this.navBriefing.click();
            await this.waitForURLContains('/briefing');
          } else {
            await this.goto('/briefing');
          }
        } catch {
          await this.goto('/briefing');
        }
      }
    } else if (['papers', 'paper', '/papers'].includes(targetLower)) {
      if (!currentUrl.includes('/papers')) {
        try {
          if (await this.navPapers.isVisible({ timeout: 3000 })) {
            await this.navPapers.click();
            await this.waitForURLContains('/papers');
          } else {
            await this.goto('/papers');
          }
        } catch {
          await this.goto('/papers');
        }
      }
    } else if (['tuning', '/tuning'].includes(targetLower)) {
      if (!currentUrl.includes('/tuning')) {
        try {
          if (await this.navTuning.isVisible({ timeout: 3000 })) {
            await this.navTuning.click();
            await this.waitForURLContains('/tuning');
          } else {
            await this.goto('/tuning');
          }
        } catch {
          await this.goto('/tuning');
        }
      }
    } else if (['ask', 'chat', '/ask'].includes(targetLower)) {
      if (!currentUrl.includes('/ask')) {
        try {
          if (await this.navAsk.isVisible({ timeout: 3000 })) {
            await this.navAsk.click();
            await this.waitForURLContains('/ask');
          } else {
            await this.goto('/ask');
          }
        } catch {
          await this.goto('/ask');
        }
      }
    } else if (['runs', 'pipeline-runs', '/runs'].includes(targetLower)) {
      if (!currentUrl.includes('/runs')) {
        try {
          if (await this.navRuns.isVisible({ timeout: 3000 })) {
            await this.navRuns.click();
            await this.waitForURLContains('/runs');
          } else {
            await this.goto('/runs');
          }
        } catch {
          await this.goto('/runs');
        }
      }
    } else if (['audit-queue', 'audit', 'queue', '/audit-queue'].includes(targetLower)) {
      if (!currentUrl.includes('/audit-queue')) {
        try {
          if (await this.navAuditQueue.isVisible({ timeout: 3000 })) {
            await this.navAuditQueue.click();
            await this.waitForURLContains('/audit-queue');
          } else {
            await this.goto('/audit-queue');
          }
        } catch {
          await this.goto('/audit-queue');
        }
      }
    } else if (['settings', '/settings'].includes(targetLower)) {
      await this.goto('/settings');
    } else {
      await this.goto(target);
    }
    await this.waitForNetworkIdle();
  }

  async openUserMenu(): Promise<boolean> {
    const menu = this.page.locator("[role='menu']");
    if (await menu.isVisible()) {
      return true;
    }
    try {
      if (await this.userMenuButton.isVisible({ timeout: 4000 })) {
        await this.userMenuButton.scrollIntoViewIfNeeded();
        await this.userMenuButton.click({ force: true });
        await this.page.waitForSelector("[role='menu']", { timeout: 4000 });
        return true;
      }
    } catch {
      // Menu might open on alternative trigger or desktop avatar
    }
    return false;
  }

  async getCurrentUserDisplayName(): Promise<string | null> {
    try {
      if (await this.userNameLabel.isVisible({ timeout: 5000 })) {
        return (await this.userNameLabel.textContent())?.trim() ?? null;
      }
    } catch {
      // Ignored
    }
    return null;
  }

  async toggleLanguage(): Promise<void> {
    const opened = await this.openUserMenu();
    if (opened && await this.menuLanguageToggle.isVisible({ timeout: 3000 })) {
      await this.menuLanguageToggle.click();
      await this.waitForNetworkIdle();
    }
  }

  async signOut(): Promise<void> {
    const opened = await this.openUserMenu();
    if (opened && await this.menuSignOutButton.isVisible({ timeout: 3000 })) {
      await this.menuSignOutButton.click();
      await this.waitForNetworkIdle();
    } else {
      // Fallback direct API logout call
      await this.page.evaluate(async () => {
        await fetch('/auth/logout', { method: 'POST' });
        window.location.assign('/');
      });
      await this.waitForNetworkIdle();
    }
  }
}

import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class WorkspaceSwitcher extends BasePage {
  readonly switcherButton: Locator;
  readonly currentWorkspaceNameLabel: Locator;
  readonly dropdownMenu: Locator;
  readonly workspaceItems: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.switcherButton = page.locator(
      "aside header button[aria-label*='workspace' i], aside button[aria-label*='workspace' i], nav button[aria-label*='workspace' i], header button[aria-label*='workspace' i], button[aria-label*='Switch workspace'], button[aria-label*='workspace' i], aside header button"
    ).first();
    this.currentWorkspaceNameLabel = page.locator(
      "aside header button span.truncate, aside header span, aside button[aria-label*='workspace' i] span.truncate, button[aria-label*='Switch workspace'] span.truncate, aside header [data-slot='text']"
    ).first();
    this.dropdownMenu = page.locator("[role='menu']");
    this.workspaceItems = page.locator("[role='menu'] [role='menuitem']");
  }

  async getCurrentWorkspaceName(): Promise<string | null> {
    try {
      if (await this.currentWorkspaceNameLabel.isVisible({ timeout: 3000 })) {
        const text = (await this.currentWorkspaceNameLabel.textContent())?.trim();
        if (text && text.length > 0) return text;
      }
    } catch {
      // Ignored
    }
    return null;
  }

  async getCurrentWorkspaceCookie(): Promise<string | undefined> {
    return this.getCookie('rs-workspace');
  }

  async openDropdown(): Promise<boolean> {
    try {
      if (await this.dropdownMenu.isVisible()) {
        return true;
      }
      if (await this.switcherButton.isVisible({ timeout: 2000 })) {
        await this.switcherButton.click();
        await this.page.waitForSelector("[role='menu']", { timeout: 2500 });
        return true;
      }
    } catch {
      // Single workspace mode: frontend renders static SidebarItem without dropdown menu
    }
    return false;
  }

  async listAvailableWorkspaces(): Promise<string[]> {
    const hasDropdown = await this.openDropdown();
    if (hasDropdown) {
      const items = await this.workspaceItems.allTextContents();
      const cleanItems = items.map((i) => i.trim()).filter((i) => i.length > 0);
      if (cleanItems.length > 0) {
        return cleanItems;
      }
    }
    // Fallback if only 1 workspace exists (no dropdown rendered)
    const currentName = await this.getCurrentWorkspaceName();
    return currentName ? [currentName] : ['default'];
  }

  async switchToWorkspace(workspaceName: string): Promise<boolean> {
    const hasDropdown = await this.openDropdown();
    if (hasDropdown) {
      const targetItem = this.page.locator(`[role='menu'] [role='menuitem']:has-text('${workspaceName}')`).first();
      if (await targetItem.isVisible({ timeout: 3000 })) {
        await targetItem.click();
        await this.waitForNetworkIdle();
        return true;
      }
    }
    const current = await this.getCurrentWorkspaceName();
    return current === workspaceName;
  }
}

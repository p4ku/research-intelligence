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
      "button[aria-label*='workspace'], button[aria-label*='Workspace'], button:has-text('test_e2e'), button:has([data-slot='icon'])"
    ).first();
    this.currentWorkspaceNameLabel = page.locator(
      "button[aria-label*='workspace'] span.truncate, button[aria-label*='Workspace'] span.truncate, button[aria-label*='workspace'] span"
    ).first();
    this.dropdownMenu = page.locator("[role='menu']");
    this.workspaceItems = page.locator("[role='menu'] [role='menuitem']");
  }

  async getCurrentWorkspaceName(): Promise<string | null> {
    try {
      if (await this.currentWorkspaceNameLabel.isVisible({ timeout: 5000 })) {
        return (await this.currentWorkspaceNameLabel.textContent())?.trim() ?? null;
      }
    } catch {
      // Ignored
    }
    return null;
  }

  async getCurrentWorkspaceCookie(): Promise<string | undefined> {
    return this.getCookie('rs-workspace');
  }

  async openDropdown(): Promise<void> {
    if (!(await this.dropdownMenu.isVisible())) {
      await this.switcherButton.click();
      await this.page.waitForSelector("[role='menu']", { timeout: 5000 });
    }
  }

  async listAvailableWorkspaces(): Promise<string[]> {
    await this.openDropdown();
    const items = await this.workspaceItems.allTextContents();
    return items.map((i) => i.trim()).filter((i) => i.length > 0);
  }

  async switchToWorkspace(workspaceName: string): Promise<boolean> {
    await this.openDropdown();
    const targetItem = this.page.locator(`[role='menu'] [role='menuitem']:has-text('${workspaceName}')`).first();
    if (await targetItem.isVisible({ timeout: 5000 })) {
      await targetItem.click();
      await this.waitForNetworkIdle();
      return true;
    }
    return false;
  }
}

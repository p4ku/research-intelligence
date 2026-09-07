import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class SettingsPage extends BasePage {
  readonly pageTitleHeading: Locator;

  // Profile Form
  readonly firstNameInput: Locator;
  readonly lastNameInput: Locator;
  readonly emailInput: Locator;
  readonly usernameInput: Locator;
  readonly saveProfileButton: Locator;

  // Password Form
  readonly currentPasswordInput: Locator;
  readonly newPasswordInput: Locator;
  readonly confirmPasswordInput: Locator;
  readonly changePasswordButton: Locator;

  // Account details
  readonly accountRoleValue: Locator;
  readonly signedInWithValue: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitleHeading = page.locator("h1:has-text('Settings'), h1:has-text('Einstellungen')").first();

    this.firstNameInput = page.locator("input[name='first_name']");
    this.lastNameInput = page.locator("input[name='last_name']");
    this.emailInput = page.locator("input[name='email']");
    this.usernameInput = page.locator("input[name='username']");
    this.saveProfileButton = page.locator("button:has-text('Save profile'), button:has-text('Profil speichern')").first();

    this.currentPasswordInput = page.locator("input[name='old_password']");
    this.newPasswordInput = page.locator("input[name='new_password']");
    this.confirmPasswordInput = page.locator("input[name='confirm_password']");
    this.changePasswordButton = page.locator("button:has-text('Change password'), button:has-text('Passwort ändern')").first();

    this.accountRoleValue = page.locator("dt:has-text('Role'), dt:has-text('Rolle')").locator('..').locator('dd');
    this.signedInWithValue = page.locator("dt:has-text('Signed in with'), dt:has-text('Angemeldet mit')").locator('..').locator('dd');
  }

  async load() {
    return this.goto('/settings');
  }

  async isLoaded(): Promise<boolean> {
    try {
      await this.pageTitleHeading.waitFor({ state: 'visible', timeout: 10000 });
      return true;
    } catch {
      return false;
    }
  }

  async getProfileValues(): Promise<Record<string, string>> {
    return {
      first_name: (await this.firstNameInput.isVisible()) ? await this.firstNameInput.inputValue() : '',
      last_name: (await this.lastNameInput.isVisible()) ? await this.lastNameInput.inputValue() : '',
      email: (await this.emailInput.isVisible()) ? await this.emailInput.inputValue() : '',
      username: (await this.usernameInput.isVisible()) ? await this.usernameInput.inputValue() : '',
    };
  }

  async updateProfile(firstName?: string, lastName?: string): Promise<boolean> {
    if (firstName !== undefined) {
      await this.firstNameInput.fill(firstName);
    }
    if (lastName !== undefined) {
      await this.lastNameInput.fill(lastName);
    }
    await this.saveProfileButton.click();
    await this.waitForNetworkIdle();
    return true;
  }

  async getAccountRole(): Promise<string | null> {
    try {
      if (await this.accountRoleValue.isVisible({ timeout: 5000 })) {
        return (await this.accountRoleValue.textContent())?.trim() ?? null;
      }
    } catch {
      // Ignored
    }
    return null;
  }

  async getSignedInWith(): Promise<string | null> {
    try {
      if (await this.signedInWithValue.isVisible({ timeout: 5000 })) {
        return (await this.signedInWithValue.textContent())?.trim() ?? null;
      }
    } catch {
      // Ignored
    }
    return null;
  }

  async isPasswordFormVisible(): Promise<boolean> {
    try {
      await this.currentPasswordInput.waitFor({ state: 'visible', timeout: 5000 });
      return await this.changePasswordButton.isVisible();
    } catch {
      return false;
    }
  }
}

import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

export class LoginPage extends BasePage {
  readonly identifierInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorAlert: Locator;
  readonly noticeBox: Locator;
  readonly signInHeading: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.identifierInput = page.locator("input[name='identifier']");
    this.passwordInput = page.locator("input[name='password']");
    this.submitButton = page.locator("button[type='submit']");
    this.errorAlert = page.locator("[role='alert'], p.text-red-600, p.text-red-400");
    this.noticeBox = page.locator("p.bg-amber-50, p.text-amber-800");
    this.signInHeading = page.locator("h1:has-text('Sign in'), h1:has-text('Anmelden')");
  }

  async load(nextPath?: string) {
    const path = nextPath ? `/?next=${encodeURIComponent(nextPath)}` : '/';
    return this.goto(path);
  }

  async isLoaded(): Promise<boolean> {
    try {
      await this.identifierInput.waitFor({ state: 'visible', timeout: 10000 });
      return true;
    } catch {
      return false;
    }
  }

  async fillCredentials(identifier: string, password: string) {
    await this.identifierInput.fill(identifier);
    await this.passwordInput.fill(password);
  }

  async submit() {
    await this.submitButton.click();
  }

  async login(identifier: string, password: string, waitForRedirect: boolean = true): Promise<boolean> {
    await this.load();
    await this.fillCredentials(identifier, password);
    await this.submit();

    if (waitForRedirect) {
      try {
        await this.page.waitForURL((url) => {
          const str = url.toString();
          return str.includes('/dashboard') || str.includes('/briefing') || str.includes('/papers');
        }, { timeout: 15000 });
        await this.waitForNetworkIdle();
        return true;
      } catch {
        return false;
      }
    }
    return true;
  }

  async getErrorMessage(): Promise<string | null> {
    try {
      if (await this.errorAlert.isVisible({ timeout: 5000 })) {
        return (await this.errorAlert.textContent())?.trim() ?? null;
      }
    } catch {
      // Ignored
    }
    return null;
  }
}

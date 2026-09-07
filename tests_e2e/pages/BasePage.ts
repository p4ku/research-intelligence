import { BrowserContext, Page, Response } from '@playwright/test';

export class BasePage {
  readonly page: Page;
  readonly baseURL: string;

  constructor(page: Page, baseURL?: string) {
    this.page = page;
    this.baseURL = (baseURL || '').replace(/\/$/, '');
  }

  async goto(path: string = '', timeout: number = 30000): Promise<Response | null> {
    const url = path.startsWith('http') ? path : `/${path.replace(/^\//, '')}`;
    return this.page.goto(url, { waitUntil: 'domcontentloaded', timeout });
  }

  async waitForURLContains(pattern: string, timeout: number = 15000): Promise<void> {
    await this.page.waitForURL((url) => url.toString().includes(pattern), { timeout });
  }

  currentURL(): string {
    return this.page.url();
  }

  currentPath(): string {
    const url = this.page.url();
    try {
      const parsed = new URL(url);
      return parsed.pathname;
    } catch {
      return url;
    }
  }

  async getCookie(name: string): Promise<string | undefined> {
    const cookies = await this.page.context().cookies();
    const found = cookies.find((c) => c.name === name);
    return found?.value;
  }

  /**
   * Seed browser cookies on this page's context. The counterpart to getCookie,
   * for preferences the app reads server-side (rs-lang, rs-features): call it
   * before the first navigation so the very first render already sees them.
   */
  async addCookies(cookies: Parameters<BrowserContext['addCookies']>[0]): Promise<void> {
    await this.page.context().addCookies(cookies);
  }

  async waitForNetworkIdle(timeout: number = 15000): Promise<void> {
    try {
      await this.page.waitForLoadState('networkidle', { timeout });
    } catch {
      // Continue if network idle timed out
    }
  }

  async reload(): Promise<void> {
    await this.page.reload({ waitUntil: 'domcontentloaded' });
  }
}

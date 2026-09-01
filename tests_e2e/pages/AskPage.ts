import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

/**
 * The Ask page. Conversations are scoped to one paper: until a paper is
 * chosen the composer is a paper picker (a combobox with a listbox beneath),
 * so asking a question means picking a paper first.
 */
export class AskPage extends BasePage {
  readonly pageTitle: Locator;
  readonly questionInput: Locator;
  readonly paperPicker: Locator;
  readonly sendButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Ask'), h1:has-text('Fragen')").first();
    this.questionInput = page.locator("textarea[name='question']").first();
    this.paperPicker = page.locator('#paper-picker');
    this.sendButton = page.locator("button[type='submit'], button:has-text('Send'), button:has-text('Senden')").first();
  }

  async load() {
    return this.goto('/ask');
  }

  async isLoaded(): Promise<boolean> {
    try {
      const url = this.currentURL();
      return url.includes('/ask') && (await this.questionInput.isVisible({ timeout: 5000 }));
    } catch {
      return false;
    }
  }

  /** Scope the conversation to the top paper in the picker, if none is chosen yet. */
  async chooseFirstPaper(): Promise<void> {
    const picking = await this.paperPicker.isVisible({ timeout: 3000 }).catch(() => false);
    if (!picking) return;
    await this.questionInput.press('Enter');
    await this.paperPicker.waitFor({ state: 'hidden', timeout: 5000 });
  }

  async askQuestion(question: string): Promise<void> {
    await this.chooseFirstPaper();
    await this.questionInput.fill(question);
    await this.questionInput.press('Enter');
    await this.waitForNetworkIdle();
  }
}

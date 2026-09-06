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
  readonly messagesList: Locator;
  readonly citationItems: Locator;
  readonly sessionItems: Locator;
  readonly openAnalysisButton: Locator;
  readonly paperSearchInput: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Ask'), h1:has-text('Fragen')").first();
    this.questionInput = page.locator("textarea[name='question'], textarea[placeholder*='Ask'], textarea[placeholder*='Frage']").first();
    this.paperPicker = page.locator('#paper-picker, [data-testid="paper-picker"]');
    this.sendButton = page.locator("button[type='submit'], button:has-text('Send'), button:has-text('Senden')").first();
    this.messagesList = page.locator("[data-testid='chat-message'], .chat-message, .message-bubble");
    this.citationItems = page.locator("[data-testid='citation-pill'], [data-testid='visual-citation'], .citation-item, .citation-badge");
    this.sessionItems = page.locator("[data-testid='session-item'], [data-testid='chat-history-item'], .session-item");
    this.openAnalysisButton = page.locator("a:has-text('Scorecard'), a:has-text('Analysis'), button:has-text('View Scorecard'), [data-testid='open-paper-analysis']").first();
    this.paperSearchInput = page.locator("input[placeholder*='Search paper'], input[placeholder*='Titel oder Autor'], #paper-search-input").first();
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

  /** Search and select a specific paper by title or author keyword */
  async searchAndSelectPaper(term: string): Promise<void> {
    const searchVisible = await this.paperSearchInput.isVisible({ timeout: 2000 }).catch(() => false);
    if (searchVisible) {
      await this.paperSearchInput.fill(term);
      await this.page.keyboard.press('Enter');
      await this.waitForNetworkIdle();
    }
    await this.chooseFirstPaper();
  }

  async askQuestion(question: string): Promise<void> {
    await this.chooseFirstPaper();
    await this.questionInput.fill(question);
    await this.questionInput.press('Enter');
    await this.waitForNetworkIdle();
  }

  async hasCitations(): Promise<boolean> {
    return (await this.citationItems.count()) > 0;
  }
}


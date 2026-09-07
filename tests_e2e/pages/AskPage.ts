import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage.js';

/**
 * The Ask page — a chat canvas. The composer takes a question straight away,
 * but the only tool wired today is "attach a paper", so sending with nothing
 * attached opens the paper picker holding the question; choosing a paper
 * sends it. Past conversations live in a sidecar that is hidden until the
 * top bar's panel button opens it.
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
  readonly recentChatsToggle: Locator;
  readonly newChatButton: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    this.pageTitle = page.locator("h1:has-text('Ask'), h1:has-text('Fragen')").first();
    this.questionInput = page.locator("textarea[name='question']").first();
    this.paperPicker = page.locator('#paper-picker');
    this.sendButton = page.locator("button[type='submit']").first();
    this.messagesList = page.locator('article');
    this.citationItems = page.locator("[data-testid='citation-pill'], [data-testid='visual-citation'], .citation-item, .citation-badge");
    this.sessionItems = page.locator("[data-row='session']");
    this.openAnalysisButton = page.locator("a:has-text('Scorecard'), a:has-text('Analysis'), button:has-text('View Scorecard'), [data-testid='open-paper-analysis']").first();
    this.recentChatsToggle = page.locator("button[aria-label='Recent chats'], button[aria-label='Letzte Chats']").first();
    this.newChatButton = page.locator("button[aria-label='New chat'], button[aria-label='Neuer Chat']").first();
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

  private async pickerVisible(timeout = 3000): Promise<boolean> {
    return this.paperPicker.isVisible({ timeout }).catch(() => false);
  }

  /** Take the top row the picker is offering, opening it first if it is closed. */
  async chooseFirstPaper(): Promise<void> {
    if (!(await this.pickerVisible(1000))) {
      // '@' on its own is the composer's way into the picker.
      await this.questionInput.fill('@');
      if (!(await this.pickerVisible(5000))) return;
    }
    await this.questionInput.press('Enter');
    await this.paperPicker.waitFor({ state: 'hidden', timeout: 5000 });
  }

  /** Search the picker for a paper and take the first match. */
  async searchAndSelectPaper(term: string): Promise<void> {
    if (!(await this.pickerVisible(1000))) {
      await this.questionInput.fill('@');
      if (!(await this.pickerVisible(5000))) return;
    }
    await this.questionInput.fill(term);
    await this.page.waitForTimeout(300);
    await this.questionInput.press('Enter');
    await this.paperPicker.waitFor({ state: 'hidden', timeout: 5000 });
  }

  async askQuestion(question: string): Promise<void> {
    await this.questionInput.fill(question);
    await this.questionInput.press('Enter');
    // With no paper attached the question is held and the picker opens;
    // choosing a paper is what actually sends it.
    if (await this.pickerVisible(3000)) {
      await this.questionInput.press('Enter');
      await this.paperPicker.waitFor({ state: 'hidden', timeout: 5000 });
    }
    await this.waitForNetworkIdle();
  }

  /** Recent conversations are behind the top bar's panel button. */
  async openRecentChats(): Promise<void> {
    if ((await this.recentChatsToggle.getAttribute('aria-expanded')) === 'true') return;
    await this.recentChatsToggle.click();
    await this.page.waitForTimeout(300);
  }

  async hasCitations(): Promise<boolean> {
    return (await this.citationItems.count()) > 0;
  }
}

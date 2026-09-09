import { BrowserContext, Locator, Page } from '@playwright/test';
import { BasePage } from './BasePage.js';

/**
 * Demo feature flags (docs/design/feature-flags.md).
 *
 * Three per-browser switches in the account menu hide a feature live and put
 * it back. They are stored in one readable cookie, `rs-features`, whose value
 * is the `.`-separated list of the flags that are OFF.
 *
 * Since 9 Sep 2026 every flag is FIXED in the registry
 * (frontend/src/lib/features.ts): `all_papers` and `ask` off, `stars` on. A
 * fixed flag ignores the cookie and has no menu row, so `row()`, `switchOf()`
 * and `setFlag()` below find nothing until a flag's `fixed` property is
 * deleted; journey 07 uses them to assert that absence.
 */
export type FeatureFlag = 'all_papers' | 'stars' | 'ask';

export const FEATURES_COOKIE = 'rs-features';

export const FEATURE_FLAGS: FeatureFlag[] = ['all_papers', 'stars', 'ask'];

/**
 * The account-menu row for each flag, in both languages: the German menu
 * reads "Alle Papers", "Markierungen", "Fragen".
 */
const ROW_LABELS: Record<FeatureFlag, RegExp> = {
  all_papers: /^(All papers|Alle Papers)$/,
  stars: /^(Stars|Markierungen)$/,
  ask: /^(Ask|Fragen)$/,
};

/**
 * Seed the flag cookie on a context before anything is loaded, which is how a
 * spec starts a session with a feature already hidden. The value is the OFF
 * list, so `[]` writes the all-on empty string. Same shape as the `rs-lang`
 * seed in frontend/scripts/lib/browser.ts.
 */
export async function addFeatureCookie(
  context: BrowserContext,
  offFlags: FeatureFlag[],
  baseURL: string,
): Promise<void> {
  await context.addCookies([
    { name: FEATURES_COOKIE, value: offFlags.join('.'), url: baseURL },
  ]);
}

/**
 * The "Demo features" section of the account menu: one menuitem per
 * non-fixed flag, each carrying a switch. A toggle row is never hidden by its
 * own flag — it is how a feature comes back — and the section does not render
 * while every flag is fixed.
 */
export class FeatureToggles extends BasePage {
  readonly accountMenuButton: Locator;
  readonly menu: Locator;
  readonly sectionHeading: Locator;

  constructor(page: Page, baseURL?: string) {
    super(page, baseURL);
    // Same union SidebarNav uses for the account button: the sidebar footer
    // item on desktop, the avatar button in the mobile header.
    this.accountMenuButton = page
      .locator(
        "aside footer button, aside footer [role='button'], aside footer [data-slot='item'], button:has([data-slot='avatar']), header button:has([data-slot='avatar'])"
      )
      .first();
    this.menu = page.locator("[role='menu']");
    this.sectionHeading = this.menu.getByText(/^(Demo features|Demo-Funktionen)$/);
  }

  /**
   * Open the account menu if it is not already open. The button is server
   * rendered but the menu is not: a click that lands before hydration is
   * simply swallowed, so this retries rather than failing the spec on a slow
   * first paint.
   */
  async openMenu(): Promise<void> {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (await this.menu.isVisible()) {
        return;
      }
      await this.accountMenuButton.scrollIntoViewIfNeeded();
      await this.accountMenuButton.click();
      try {
        await this.menu.waitFor({ state: 'visible', timeout: 5000 });
        return;
      } catch {
        // Not hydrated yet — click again.
      }
    }
    await this.menu.waitFor({ state: 'visible', timeout: 5000 });
  }

  /** Close the account menu (the rows deliberately keep it open on click). */
  async closeMenu(): Promise<void> {
    if (await this.menu.isVisible()) {
      await this.page.keyboard.press('Escape');
      await this.menu.waitFor({ state: 'hidden', timeout: 10000 });
    }
  }

  /** The menu row for a flag. Requires the menu to be open. */
  row(flag: FeatureFlag): Locator {
    return this.menu.getByRole('menuitem', { name: ROW_LABELS[flag] });
  }

  /** The switch inside that row; `aria-checked` is the flag's state. */
  switchOf(flag: FeatureFlag): Locator {
    return this.row(flag).getByRole('switch');
  }

  /** Whether the flag currently reads as on in the menu. */
  async isOn(flag: FeatureFlag): Promise<boolean> {
    await this.openMenu();
    return (await this.switchOf(flag).getAttribute('aria-checked')) === 'true';
  }

  /**
   * Flip a flag to the wanted state from the account menu, the way the product
   * owner does mid-demo. A no-op if it is already there.
   *
   * Turning off the flag that owns the current route navigates the browser to
   * /dashboard (the vanish guard), so callers standing on /papers or /ask must
   * expect the URL to change; everywhere else this is a server refresh and the
   * menu stays open.
   */
  async setFlag(flag: FeatureFlag, on: boolean): Promise<void> {
    await this.openMenu();
    if ((await this.isOn(flag)) === on) {
      return;
    }
    await this.row(flag).click();
  }

  async turnOff(flag: FeatureFlag): Promise<void> {
    await this.setFlag(flag, false);
  }

  async turnOn(flag: FeatureFlag): Promise<void> {
    await this.setFlag(flag, true);
  }

  /** The raw cookie value: the OFF list, '' when everything is on. */
  async featuresCookie(): Promise<string | undefined> {
    return this.getCookie(FEATURES_COOKIE);
  }
}

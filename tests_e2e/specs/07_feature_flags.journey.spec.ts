import { test, expect, Page } from '@playwright/test';
import {
  BriefingPage,
  FEATURE_FLAGS,
  FeatureFlag,
  FeatureToggles,
  LoginPage,
  addFeatureCookie,
} from '../pages/index.js';

/**
 * Journey 7: Demo feature flags (docs/design/feature-flags.md).
 *
 * Since 9 Sep 2026 every flag is FIXED in the registry
 * (frontend/src/lib/features.ts): `all_papers` and `ask` are off, `stars` is
 * on, and the "Demo features" section of the account menu does not render. The
 * `rs-features` cookie still exists, but a fixed flag ignores it — so this
 * journey asserts the fixed state, and that a cookie cannot move it either
 * way. Delete the `fixed` properties to hand the switches back; the previous
 * version of this spec (git history) covered the toggles.
 *
 * Everything here asserts ABSENCE, and it does so with raw locators on
 * purpose. Two page-object helpers are false-green traps for a hidden route
 * and are deliberately not used below:
 *   - SidebarNav.navigateTo() falls back to goto(path) when the nav link is
 *     missing, so a hidden route would still be "navigated to" — into a 404.
 *   - PapersPage.isLoaded() returns true on the not-found card, because that
 *     card renders inside the shell's <main>.
 */

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

/** The shared not-found card, in both languages. */
const NOT_FOUND_COPY = /We couldn't find that\.|Das konnten wir nicht finden\./;

/** Star affordances: the card/masthead buttons and the list "Starred" chip.
 *  German reads merken / gemerkt / Merkliste since 9 Sep 2026. */
const STAR_CONTROL =
  /Star this paper|Unstar this paper|Star this briefing|Unstar this briefing|Starred|merken|Merkliste|Gemerkt/;

/** The rows the rail shows today; /papers and /ask are the hidden ones. */
const NAV_HREFS = ['/dashboard', '/briefing', '/runs'];
const HIDDEN_HREFS = ['/papers', '/ask'];

/** Nav rows, rail and drawer alike — never the page-object helper. */
function navLink(page: Page, href: string) {
  return page.locator(`nav a[href='${href}'], aside a[href='${href}']`);
}

/**
 * Sign in with the flag cookie already seeded, so the very first server render
 * sees it. Pass [] for the default, all-on browser.
 */
async function signInWithFlagsOff(page: Page, baseURL: string, offFlags: FeatureFlag[]) {
  if (offFlags.length > 0) {
    await addFeatureCookie(page.context(), offFlags, baseURL);
  }
  // The form comes from the page object; the wait is written out here rather
  // than through LoginPage.login(), which returns false on a slow sign-in and
  // would fail this spec with "expected true" instead of a locator. Submitting
  // before the form hydrates posts it natively (the credentials land in the
  // query string and nothing else happens), so the attempt is simply retried.
  const loginPage = new LoginPage(page);
  for (let attempt = 0; attempt < 3; attempt++) {
    await loginPage.load();
    await loginPage.fillCredentials(USERNAME, PASSWORD);
    await loginPage.submit();
    try {
      await page.waitForURL((url) => new URL(url.toString()).pathname === '/dashboard', {
        timeout: 20000,
      });
      return;
    } catch {
      // Not signed in — try the form again.
    }
  }
  throw new Error(`Could not sign in as ${USERNAME}`);
}

/**
 * Open a paper the way the product still allows: newest briefing, first card.
 * Home lists briefings, not papers, and /papers is gone, so this is the road.
 * BriefingPage's openers throw on a regression and return null only when the
 * environment has nothing briefed, which the caller logs as a skip.
 */
async function openAPaper(page: Page): Promise<string | null> {
  const briefing = new BriefingPage(page);
  await page.goto('/briefing', { waitUntil: 'domcontentloaded' });
  const editionUrl = await briefing.openFirstEdition();
  if (!editionUrl) return null;
  if ((await briefing.firstCardScore()) === null) return null;
  return briefing.openFirstCard();
}

test.describe('Journey 7: Demo feature flags (all_papers, ask fixed off; stars fixed on)', () => {
  test('Fixed state: three nav rows, /papers and /ask are the not-found card, no corpus search, stars on, no toggles', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, []);

    console.log('📍 Step 1: No flag cookie is written by simply signing in...');
    const toggles = new FeatureToggles(page);
    expect(await toggles.featuresCookie()).toBeUndefined();

    console.log('📍 Step 2: The rail shows Home, Briefings and Runs, and nothing for /papers or /ask...');
    for (const href of NAV_HREFS) {
      await expect(navLink(page, href).first()).toBeVisible();
    }
    for (const href of HIDDEN_HREFS) {
      await expect(navLink(page, href)).toHaveCount(0);
    }
    await expect(page.locator('nav a, aside a').filter({ hasText: /^Papers$/ })).toHaveCount(0);
    await expect(page.locator('nav a, aside a').filter({ hasText: /^(Ask|Fragen)$/ })).toHaveCount(0);

    console.log('📍 Step 3: ...and so does the mobile drawer, which is a second render path...');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: /Open navigation|Navigation öffnen/ }).click();
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByRole('link', { name: /^(Home|Start)$/ })).toBeVisible();
    for (const href of HIDDEN_HREFS) {
      await expect(drawer.locator(`a[href='${href}']`)).toHaveCount(0);
    }
    await page.getByRole('button', { name: /Close navigation|Navigation schlie/ }).click();
    await page.setViewportSize({ width: 1440, height: 900 });

    console.log("📍 Step 4: Home's corpus search is gone whole...");
    await expect(page.getByRole('combobox', { name: /Search papers|Papers durchsuchen/ })).toHaveCount(0);

    console.log('📍 Step 5: A pasted /papers URL lands on the shared not-found card...');
    await page.goto('/papers', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(NOT_FOUND_COPY)).toBeVisible();
    await expect(page.locator("main a[href^='/papers/']")).toHaveCount(0);
    // The card must not offer a button into another 404.
    await expect(page.getByRole('link', { name: /Go to Papers|Zu Papers/ })).toHaveCount(0);
    await expect(page.getByRole('link', { name: /Go to Briefings|Zu den Briefings/ })).toBeVisible();

    console.log('📍 Step 6: A pasted /ask URL is the not-found card, streamed inside a 200...');
    // 200 is the decision, not an accident: /ask has a loading.tsx, so the
    // shell has already flushed by the time notFound() runs (design §3.6).
    const response = await page.goto('/ask', { waitUntil: 'domcontentloaded' });
    expect(response?.status()).toBe(200);
    await expect(page.getByText(NOT_FOUND_COPY)).toBeVisible();
    const inbound = await page.goto('/ask?q=x&paper=missing', { waitUntil: 'domcontentloaded' });
    expect(inbound?.status()).toBe(200);
    await expect(page.getByText(NOT_FOUND_COPY)).toBeVisible();

    console.log('📍 Step 7: A paper is still readable from its briefing, keeps its star, and never links to /papers...');
    const paperUrl = await openAPaper(page);
    if (!paperUrl) {
      console.log('  ⏭ SKIPPED: no briefing with papers in this environment.');
    } else {
      expect(paperUrl).toMatch(/^\/papers\/[0-9a-f-]{36}/);
      await expect(page.getByText(NOT_FOUND_COPY)).toHaveCount(0);
      // data-state='loaded' scopes past the streamed skeleton row, which
      // carries the same data-shape.
      await expect(page.locator("[data-shape='paper-nav'][data-state='loaded']")).toBeVisible();
      expect(await page.getByRole('button', { name: STAR_CONTROL }).count()).toBeGreaterThan(0);
      await expect(page.locator("[data-shape='paper-nav'] a[href='/papers']")).toHaveCount(0);
    }

    console.log('📍 Step 8: The account menu has no Demo features section and no switches.');
    await toggles.openMenu();
    await expect(toggles.menu).toBeVisible();
    await expect(toggles.sectionHeading).toHaveCount(0);
    for (const flag of FEATURE_FLAGS) {
      await expect(toggles.row(flag)).toHaveCount(0);
    }
    // The language switch is still there: the menu lost a section, not its rows.
    await expect(toggles.menu.getByRole('menuitem', { name: /^Deutsch$/ })).toBeVisible();
  });

  test('A seeded cookie moves nothing: stars stay on, /papers and /ask stay hidden', async ({
    page,
    baseURL,
  }) => {
    // The old all-three-off value: it would have hidden every star affordance.
    await signInWithFlagsOff(page, baseURL!, [...FEATURE_FLAGS]);

    console.log('📍 Step 1: The cookie is there, so the server saw it...');
    const toggles = new FeatureToggles(page);
    expect(await toggles.featuresCookie()).toBe('all_papers.stars.ask');

    console.log('📍 Step 2: ...and the rail reads exactly as without it...');
    for (const href of NAV_HREFS) {
      await expect(navLink(page, href).first()).toBeVisible();
    }
    for (const href of HIDDEN_HREFS) {
      await expect(navLink(page, href)).toHaveCount(0);
    }

    console.log('📍 Step 3: ...with the star still on the paper masthead.');
    const paperUrl = await openAPaper(page);
    if (!paperUrl) {
      console.log('  ⏭ SKIPPED: no briefing with papers in this environment.');
    } else {
      await expect(page.locator("[data-shape='paper-nav'][data-state='loaded']")).toBeVisible();
      expect(await page.getByRole('button', { name: STAR_CONTROL }).count()).toBeGreaterThan(0);
    }
  });
});

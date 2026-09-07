import { test, expect, Page } from '@playwright/test';
import { FeatureFlag, FeatureToggles, LoginPage, addFeatureCookie } from '../pages/index.js';

/**
 * Journey 7: Demo feature flags (docs/design/feature-flags.md).
 *
 * Three per-browser switches in the account menu hide a feature live and put
 * it back: `all_papers` (the /papers corpus list), `stars` (every star
 * affordance) and `ask` (the /ask canvas and its entry points). They live in
 * one readable cookie, `rs-features`, whose value is the `.`-separated list of
 * the flags that are OFF; absent or empty means the whole product.
 *
 * Everything here asserts ABSENCE, and it does so with raw locators on
 * purpose. Two page-object helpers are false-green traps for a flag-off run
 * and are deliberately not used below:
 *   - SidebarNav.navigateTo() falls back to goto(path) when the nav link is
 *     missing, so a hidden route would still be "navigated to" — into a 404.
 *   - PapersPage.isLoaded() returns true on the not-found card, because that
 *     card renders inside the shell's <main>.
 *
 * The rest of the suite runs cookieless and therefore sees the full product;
 * the first test below states that assumption out loud.
 */

const USERNAME = process.env.E2E_USERNAME || process.env.TEST_USERNAME || 'test_e2e';
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PASSWORD || 't4st_pa55w0rD!#';

/** The shared not-found card, in both languages. */
const NOT_FOUND_COPY = /We couldn't find that\.|Das konnten wir nicht finden\./;

/** The search panel's Ask row: `Ask about “{title}”` / `Zu „{title}“ fragen`. */
const ASK_ROW = /Ask about|fragen/i;

/** Star affordances: the card/masthead buttons and the list "Starred" chip. */
const STAR_CONTROL =
  /Star this paper|Unstar this paper|Star this briefing|Unstar this briefing|Starred|Markiert/;

const NAV_HREFS = ['/dashboard', '/briefing', '/papers', '/ask', '/runs'];

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

/** A word from a real paper title on Home, so the search panel has a hit. */
async function paperSearchTerm(page: Page): Promise<string> {
  const texts = await page.locator("main a[href^='/papers/']").allInnerTexts();
  for (const text of texts) {
    const word = text
      .split(/\s+/)
      .map((piece) => piece.replace(/[^A-Za-z]/g, ''))
      .find((piece) => piece.length >= 5);
    if (word) {
      return word;
    }
  }
  return 'learning';
}

/** Type into Home's corpus search and wait for the panel to answer. */
async function openSearchPanel(page: Page, term: string) {
  const box = page.getByRole('combobox', { name: /Search papers|Papers durchsuchen/ });
  await expect(box).toBeVisible();
  // Typing into the field before it hydrates changes the input and nothing
  // else, so wait for the request the panel makes and type again if it never
  // comes. The assertions that follow are absolute either way.
  for (let attempt = 0; attempt < 3; attempt++) {
    const answered = page.waitForResponse(
      (response) => response.url().includes('/bff/search?q=') && response.status() === 200,
      { timeout: 15000 }
    );
    await box.click();
    await box.fill('');
    await box.pressSequentially(term, { delay: 40 });
    try {
      await answered;
      // The panel only renders rows once the response lands.
      await expect(page.getByRole('option').first()).toBeVisible();
      return;
    } catch {
      // Not hydrated yet — type it again.
    }
  }
  throw new Error(`Corpus search never answered for "${term}"`);
}

test.describe('Journey 7: Demo feature flags (all_papers, stars, ask)', () => {
  test('Default browser: no rs-features cookie, all five nav rows and every entry point present', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, []);

    console.log('📍 Step 1: No flag cookie is written by simply signing in...');
    const toggles = new FeatureToggles(page);
    expect(await toggles.featuresCookie()).toBeUndefined();

    console.log('📍 Step 2: All five nav rows are present...');
    for (const href of NAV_HREFS) {
      await expect(navLink(page, href).first()).toBeVisible();
    }

    console.log('📍 Step 3: Home offers the corpus search and an Ask row for a paper hit...');
    const term = await paperSearchTerm(page);
    await openSearchPanel(page, term);
    await expect(page.getByRole('option').filter({ hasText: ASK_ROW })).toHaveCount(1);
    await page.keyboard.press('Escape');

    console.log('📍 Step 4: /papers is the corpus list, with star affordances on it...');
    await page.goto('/papers', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(NOT_FOUND_COPY)).toHaveCount(0);
    await expect(page.locator("main a[href^='/papers/']").first()).toBeVisible();
    expect(await page.getByRole('button', { name: STAR_CONTROL }).count()).toBeGreaterThan(0);

    console.log('📍 Step 5: The three switches read on in the account menu...');
    await toggles.openMenu();
    await expect(toggles.sectionHeading).toBeVisible();
    for (const flag of ['all_papers', 'stars', 'ask'] as FeatureFlag[]) {
      await expect(toggles.switchOf(flag)).toHaveAttribute('aria-checked', 'true');
    }
  });

  test('all_papers off: no Papers nav row, /papers is the not-found card, no corpus search, paper detail keeps one exit', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, ['all_papers']);

    console.log('📍 Step 1: The Papers row is gone from the desktop rail...');
    await expect(navLink(page, '/papers')).toHaveCount(0);
    await expect(page.locator('nav a, aside a').filter({ hasText: /^Papers$/ })).toHaveCount(0);
    // The other rows are untouched — the filter must not take the shell with it.
    await expect(navLink(page, '/briefing').first()).toBeVisible();
    await expect(navLink(page, '/ask').first()).toBeVisible();

    console.log('📍 Step 2: ...and from the mobile drawer, which is a second render path...');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: /Open navigation|Navigation öffnen/ }).click();
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByRole('link', { name: /^(Home|Heute)$/ })).toBeVisible();
    await expect(drawer.locator("a[href='/papers']")).toHaveCount(0);
    await page.getByRole('button', { name: /Close navigation|Navigation schlie/ }).click();
    await page.setViewportSize({ width: 1440, height: 900 });

    console.log('📍 Step 3: A pasted /papers URL lands on the shared not-found card...');
    await page.goto('/papers', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(NOT_FOUND_COPY)).toBeVisible();
    await expect(page.locator("main a[href^='/papers/']")).toHaveCount(0);
    // The card must not offer a button into another 404.
    await expect(page.getByRole('link', { name: /Go to Papers|Zu Papers/ })).toHaveCount(0);
    await expect(page.getByRole('link', { name: /Go to Briefings|Zu den Briefings/ })).toBeVisible();

    console.log("📍 Step 4: Home's corpus search is gone whole...");
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('combobox', { name: /Search papers|Papers durchsuchen/ })).toHaveCount(0);

    console.log('📍 Step 5: A paper is still readable, and still has exactly one exit...');
    const firstPaper = page.locator("main a[href^='/papers/']").first();
    await expect(firstPaper).toBeVisible();
    const href = await firstPaper.getAttribute('href');
    await page.goto(href!, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(NOT_FOUND_COPY)).toHaveCount(0);
    // Scoped to the row on purpose: SidebarNav.navBriefing's locator union
    // overlaps this link, so the page object would not prove anything here.
    // data-state='loaded' scopes past the streamed skeleton row, which carries
    // the same data-shape.
    await expect(
      page.locator("[data-shape='paper-nav'][data-state='loaded'] a[href='/briefing']")
    ).toBeVisible();
    await expect(page.locator("[data-shape='paper-nav'] a[href='/papers']")).toHaveCount(0);
  });

  test('stars off: no star buttons and no Starred chip anywhere on the corpus list', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, ['stars']);

    console.log('📍 Step 1: stars owns no route, so /papers is untouched...');
    await page.goto('/papers', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(NOT_FOUND_COPY)).toHaveCount(0);
    await expect(navLink(page, '/papers').first()).toBeVisible();
    // Papers really are listed: without this the star assertion is vacuous.
    await expect(page.locator("main a[href^='/papers/']").first()).toBeVisible();

    console.log('📍 Step 2: every star affordance is gone from the list...');
    await expect(page.getByRole('button', { name: STAR_CONTROL })).toHaveCount(0);

    console.log('📍 Step 3: ...and from the paper masthead...');
    const href = await page.locator("main a[href^='/papers/']").first().getAttribute('href');
    await page.goto(href!, { waitUntil: 'domcontentloaded' });
    await expect(page.locator("[data-shape='paper-nav'][data-state='loaded']")).toBeVisible();
    await expect(page.getByRole('button', { name: STAR_CONTROL })).toHaveCount(0);

    console.log('📍 Step 4: ...and from the briefings ledger.');
    await page.goto('/briefing', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(NOT_FOUND_COPY)).toHaveCount(0);
    await expect(page.getByRole('button', { name: STAR_CONTROL })).toHaveCount(0);
  });

  test('ask off: no Ask nav row, /ask is the not-found card inside an HTTP 200, no Ask row in the search panel', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, ['ask']);

    console.log('📍 Step 1: The Ask row is gone from the nav...');
    await expect(navLink(page, '/ask')).toHaveCount(0);
    await expect(page.locator('nav a, aside a').filter({ hasText: /^(Ask|Fragen)$/ })).toHaveCount(0);
    await expect(navLink(page, '/papers').first()).toBeVisible();

    console.log('📍 Step 2: A pasted /ask URL is the not-found card, streamed inside a 200...');
    // 200 is the decision, not an accident: /ask has a loading.tsx, so the
    // shell has already flushed by the time notFound() runs (design §3.6).
    const response = await page.goto('/ask', { waitUntil: 'domcontentloaded' });
    expect(response?.status()).toBe(200);
    await expect(page.getByText(NOT_FOUND_COPY)).toBeVisible();

    console.log('📍 Step 3: ...including the ?q=&paper= inbound form...');
    const inbound = await page.goto('/ask?q=x&paper=missing', { waitUntil: 'domcontentloaded' });
    expect(inbound?.status()).toBe(200);
    await expect(page.getByText(NOT_FOUND_COPY)).toBeVisible();

    console.log("📍 Step 4: Home's search panel still searches, but offers no Ask row.");
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    const term = await paperSearchTerm(page);
    await openSearchPanel(page, term);
    // The panel answered with real rows, so the absence below is a real absence.
    await expect(page.getByRole('option').filter({ hasText: new RegExp(term, 'i') }).first()).toBeVisible();
    await expect(page.getByRole('option').filter({ hasText: ASK_ROW })).toHaveCount(0);
  });

  test('Account menu: flipping a flag off removes its nav row, and flipping it back on restores it', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, []);
    const toggles = new FeatureToggles(page);

    console.log('📍 Step 1: The Demo features section is in the account menu...');
    await toggles.openMenu();
    await expect(toggles.sectionHeading).toBeVisible();
    await expect(toggles.row('ask')).toBeVisible();
    await expect(toggles.switchOf('ask')).toHaveAttribute('aria-checked', 'true');

    console.log('📍 Step 2: Flipping Ask off removes the nav row without leaving /dashboard...');
    await toggles.turnOff('ask');
    await expect(navLink(page, '/ask')).toHaveCount(0);
    await expect(toggles.switchOf('ask')).toHaveAttribute('aria-checked', 'false');
    expect(await toggles.featuresCookie()).toBe('ask');
    expect(page.url()).toContain('/dashboard');

    console.log('📍 Step 3: Flipping it back on restores the row (the untested half).');
    await toggles.turnOn('ask');
    await expect(navLink(page, '/ask').first()).toBeVisible();
    await expect(toggles.switchOf('ask')).toHaveAttribute('aria-checked', 'true');
    expect(await toggles.featuresCookie()).toBe('');
  });

  test('Vanish guard: flipping all_papers off while standing on /papers navigates to /dashboard', async ({
    page,
    baseURL,
  }) => {
    await signInWithFlagsOff(page, baseURL!, []);

    console.log('📍 Step 1: Standing on the route the flag owns...');
    await page.goto('/papers', { waitUntil: 'domcontentloaded' });
    await expect(page.locator("main a[href^='/papers/']").first()).toBeVisible();

    console.log('📍 Step 2: Flipping All papers off from the account menu...');
    const toggles = new FeatureToggles(page);
    await toggles.turnOff('all_papers');

    console.log('📍 Step 3: ...lands on /dashboard, with no 404 card under the reader.');
    await page.waitForURL((url) => new URL(url.toString()).pathname === '/dashboard', {
      timeout: 30000,
    });
    await expect(page.getByText(NOT_FOUND_COPY)).toHaveCount(0);
    await expect(navLink(page, '/papers')).toHaveCount(0);
  });
});

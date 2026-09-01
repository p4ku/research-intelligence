/**
 * Shared Playwright plumbing for the visual tooling: `scripts/screenshots.ts`
 * (contact sheets) and `scripts/skeleton-drift.ts` (skeleton geometry checks).
 * Owns the viewport matrix, context construction (theme/lang/reduced motion),
 * the real-form login, and page settling. Pure library — no side effects.
 */
import type { Browser, BrowserContext, Page } from 'playwright'

export type Lang = 'en' | 'de'
export type Theme = 'light' | 'dark'

/** The option subset the browser plumbing needs; CLI scripts extend it. */
export interface BrowserOptions {
  url: string
  user: string
  password: string
  lang: Lang | null
  theme: Theme
  scale: number | null
  timeout: number
}

export interface Viewport {
  width: number
  height: number
  deviceScaleFactor: number
  isMobile: boolean
}

export const VIEWPORTS: Record<string, Viewport> = {
  mobile: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true }, // iPhone 14/15
  tablet: { width: 834, height: 1194, deviceScaleFactor: 2, isMobile: true }, // iPad Air, portrait
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false },
}

export async function settle(page: Page, timeout: number) {
  await page.waitForLoadState('load', { timeout }).catch(() => {})
  // Dev servers keep HMR sockets open, so networkidle can never arrive; cap it.
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {})
  await page.evaluate(() => document.fonts.ready).catch(() => {})
  // Hide the Next.js dev indicator (bottom-left "N" badge) on dev-server captures.
  await page.addStyleTag({ content: 'nextjs-portal{display:none!important}' }).catch(() => {})
  await page.waitForTimeout(300)
}

export async function newContext(
  browser: Browser,
  opts: BrowserOptions,
  viewport: Viewport,
): Promise<BrowserContext> {
  const ctx = await browser.newContext({
    baseURL: opts.url,
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: opts.scale ?? viewport.deviceScaleFactor,
    isMobile: viewport.isMobile,
    hasTouch: viewport.isMobile,
    reducedMotion: 'reduce',
    colorScheme: opts.theme,
    locale: opts.lang === 'de' ? 'de-DE' : 'en-GB',
    timezoneId: 'Europe/Berlin',
  })
  ctx.setDefaultTimeout(opts.timeout)
  if (opts.lang) {
    await ctx.addCookies([{ name: 'rs-lang', value: opts.lang, url: opts.url }])
  }
  if (opts.theme === 'dark') {
    await ctx.addInitScript(() => document.documentElement.classList.add('dark'))
  }
  return ctx
}

/** Log in through the real form once; returns the session cookies. */
export async function login(browser: Browser, opts: BrowserOptions) {
  const ctx = await newContext(browser, opts, VIEWPORTS.desktop)
  const page = await ctx.newPage()
  try {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.locator("input[name='identifier']").fill(opts.user)
    await page.locator("input[name='password']").fill(opts.password)
    await page.locator("button[type='submit']").click()
    await page.waitForURL((u) => u.pathname !== '/', { timeout: opts.timeout })
    await settle(page, opts.timeout)
    const cookies = await ctx.cookies()
    if (!cookies.some((c) => c.name === 'sri_access')) {
      throw new Error('no sri_access cookie after sign-in')
    }
    return cookies
  } catch (err) {
    const alert = await page
      .locator("[role='alert']")
      .first()
      .textContent({ timeout: 1_000 })
      .catch(() => null)
    throw new Error(
      `Login failed at ${opts.url} as ${opts.user}: ${alert?.trim() || (err as Error).message}` +
        ' (against a real Django set SCREENSHOT_PASSWORD — see local-docs/backend-frontend-seam.md; the replay accepts any password)',
    )
  } finally {
    await ctx.close()
  }
}

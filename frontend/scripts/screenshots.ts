#!/usr/bin/env bun
/**
 * Screenshot every screen of the app at mobile and desktop widths with
 * Playwright, into `screenshots/<stamp>/{mobile,desktop}/NN-<name>.png`, plus
 * a `manifest.json`, a side-by-side `index.html` contact sheet and a
 * `screenshots/latest` symlink.
 *
 * Needs a running app (`bun run dev` against the replay or a real backend —
 * see local-docs/snapshot-replay.md). Logs in once through the real form, then
 * reuses the cookies for every viewport. Dynamic routes (`/briefing/[date]`,
 * `/papers/[id]`) are discovered from the first link on their list page.
 *
 *   bun run screenshots                              # http://localhost:3009, mobile + desktop
 *   bun run screenshots --url http://localhost:3010  # another dev server
 *   bun run screenshots --viewports desktop          # one viewport
 *   bun run screenshots --routes papers,ask          # subset of screens, by name
 *   bun run screenshots --lang de --theme dark       # German UI, `.dark` on <html>
 *   bun run screenshots --no-full-page --headed      # viewport-only, visible browser
 *
 * Env: SCREENSHOT_URL, SCREENSHOT_USER, SCREENSHOT_PASSWORD, SCREENSHOT_OUT.
 * Any credentials work against the replay server; a real Django needs the
 * real ones. `screenshots/` is git-ignored.
 */
import { mkdir, rm, symlink, writeFile } from 'node:fs/promises'
import { join, relative, resolve, sep } from 'node:path'
import { chromium, type Browser, type BrowserContext, type Page } from 'playwright'

// ---------------------------------------------------------------- arguments

type Lang = 'en' | 'de'
type Theme = 'light' | 'dark'

interface Options {
  url: string
  user: string
  password: string
  out: string
  viewports: string[]
  routes: string[] | null
  lang: Lang | null
  theme: Theme
  fullPage: boolean
  headed: boolean
  scale: number | null
  timeout: number
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    url: process.env.SCREENSHOT_URL ?? 'http://localhost:3009',
    user: process.env.SCREENSHOT_USER ?? 'admin',
    // The replay server accepts any password; a real Django needs the real one
    // via $SCREENSHOT_PASSWORD (see local-docs/backend-frontend-seam.md).
    password: process.env.SCREENSHOT_PASSWORD ?? 'replay',
    out: process.env.SCREENSHOT_OUT ?? '',
    viewports: ['mobile', 'desktop'],
    routes: null,
    lang: null,
    theme: 'light',
    fullPage: true,
    headed: false,
    scale: null,
    timeout: 30_000,
  }
  const next = (i: number, flag: string): string => {
    const v = argv[i + 1]
    if (v === undefined || v.startsWith('--')) throw new Error(`${flag} needs a value`)
    return v
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    switch (a) {
      case '--url':
        opts.url = next(i++, a)
        break
      case '--user':
        opts.user = next(i++, a)
        break
      case '--password':
        opts.password = next(i++, a)
        break
      case '--out':
        opts.out = next(i++, a)
        break
      case '--viewports':
        opts.viewports = next(i++, a)
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        break
      case '--routes':
        opts.routes = next(i++, a)
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        break
      case '--lang':
        opts.lang = next(i++, a) as Lang
        break
      case '--theme':
        opts.theme = next(i++, a) as Theme
        break
      case '--scale':
        opts.scale = Number(next(i++, a))
        break
      case '--timeout':
        opts.timeout = Number(next(i++, a))
        break
      case '--no-full-page':
        opts.fullPage = false
        break
      case '--headed':
        opts.headed = true
        break
      case '--help':
      case '-h':
        console.log(usage())
        process.exit(0)
      default:
        throw new Error(`Unknown argument ${a}\n${usage()}`)
    }
  }
  opts.url = opts.url.replace(/\/+$/, '')
  for (const v of opts.viewports) {
    if (!(v in VIEWPORTS))
      throw new Error(`Unknown viewport "${v}" (${Object.keys(VIEWPORTS).join(', ')})`)
  }
  if (opts.lang && !['en', 'de'].includes(opts.lang)) throw new Error('--lang must be en or de')
  if (opts.scale !== null && (!Number.isFinite(opts.scale) || opts.scale <= 0))
    throw new Error('--scale must be a positive number')
  if (!Number.isFinite(opts.timeout) || opts.timeout <= 0)
    throw new Error('--timeout must be a positive number of milliseconds')
  if (opts.routes && !SCREENS.some((s) => wanted(s, opts)))
    throw new Error(
      `--routes matched no screens. Use screen names or route templates: ${SCREENS.map((s) => s.name).join(', ')}`,
    )
  if (!['light', 'dark'].includes(opts.theme)) throw new Error('--theme must be light or dark')
  if (!opts.out) {
    const stamp = new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15)
    opts.out = join(import.meta.dir, '..', 'screenshots', stamp)
  }
  return opts
}

function usage(): string {
  return `Usage: bun run screenshots [options]
  --url <origin>          app origin (default $SCREENSHOT_URL or http://localhost:3009)
  --user/--password       login (default admin / $SCREENSHOT_PASSWORD; anything works on the replay)
  --out <dir>             output dir (default screenshots/<stamp>)
  --viewports <list>      ${Object.keys(VIEWPORTS).join(',')} (default mobile,desktop)
  --routes <list>         only these screens by name, e.g. papers,paper-detail,nav-open
  --lang en|de            set the rs-lang cookie
  --theme light|dark      add the .dark class to <html>
  --scale <n>             device scale factor for every viewport
  --no-full-page          capture the viewport only
  --headed                show the browser
  --timeout <ms>          per-navigation timeout (default 30000)`
}

// ---------------------------------------------------------------- viewports

interface Viewport {
  width: number
  height: number
  deviceScaleFactor: number
  isMobile: boolean
}

const VIEWPORTS: Record<string, Viewport> = {
  mobile: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true }, // iPhone 14/15
  tablet: { width: 834, height: 1194, deviceScaleFactor: 2, isMobile: true }, // iPad Air, portrait
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false },
}

// ---------------------------------------------------------------- screens

/**
 * Every screen in the app, in the order they should appear. `[date]` and
 * `[id]` are filled in by `discover()`. `interact` runs before the shot;
 * `only` restricts a screen to some viewports (the mobile nav is `lg:hidden`).
 */
interface Screen {
  name: string
  route: string
  auth: boolean
  only?: string[]
  viewportOnly?: boolean
  interact?: (page: Page) => Promise<void>
}

const SCREENS: Screen[] = [
  { name: 'login', route: '/', auth: false },
  { name: 'dashboard', route: '/dashboard', auth: true },
  {
    name: 'nav-open',
    route: '/nav-open',
    auth: true,
    only: ['mobile', 'tablet'],
    viewportOnly: true,
    interact: async (page) => {
      await page.getByRole('button', { name: 'Open navigation' }).click()
      await page
        .locator('[role="dialog"] nav, [role="dialog"] a[href="/dashboard"]')
        .first()
        .waitFor()
      await page.waitForTimeout(400) // Headless UI slide-in
    },
  },
  { name: 'briefing', route: '/briefing', auth: true },
  { name: 'briefing-edition', route: '/briefing/[date]', auth: true },
  { name: 'briefing-run', route: '/briefing/[date]/run', auth: true },
  { name: 'papers', route: '/papers', auth: true },
  { name: 'paper-detail', route: '/papers/[id]', auth: true },
  { name: 'ask', route: '/ask', auth: true },
  { name: 'settings', route: '/settings', auth: true },
]

/** `/nav-open` is a pseudo-route: it renders /dashboard with the drawer open. */
const PSEUDO_ROUTES: Record<string, string> = { '/nav-open': '/dashboard' }

// ---------------------------------------------------------------- helpers

interface Shot {
  name: string
  route: string
  url: string
  viewport: string
  file: string | null
  status: number | null
  finalUrl: string | null
  error: string | null
  /** CSS px the document is wider than the viewport — a horizontal-overflow bug. */
  overflowX: number
  /** Full-page capture was cut at Chromium's texture limit. */
  truncated: boolean
}

/** Chromium refuses captures above ~16384 device px on a side. */
const MAX_DEVICE_PX = 16_000

function log(msg: string) {
  console.log(msg)
}

async function settle(page: Page, timeout: number) {
  await page.waitForLoadState('load', { timeout }).catch(() => {})
  // Dev servers keep HMR sockets open, so networkidle can never arrive; cap it.
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {})
  await page.evaluate(() => document.fonts.ready).catch(() => {})
  // Hide the Next.js dev indicator (bottom-left "N" badge) on dev-server captures.
  await page.addStyleTag({ content: 'nextjs-portal{display:none!important}' }).catch(() => {})
  await page.waitForTimeout(300)
}

async function newContext(
  browser: Browser,
  opts: Options,
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
async function login(browser: Browser, opts: Options) {
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

/** Find one real `[date]` and `[id]` from the list pages. */
async function discover(
  browser: Browser,
  opts: Options,
  cookies: Awaited<ReturnType<typeof login>>,
) {
  const ctx = await newContext(browser, opts, VIEWPORTS.desktop)
  await ctx.addCookies(cookies)
  const page = await ctx.newPage()
  const firstHref = async (path: string, prefix: string): Promise<string | null> => {
    await page.goto(path, { waitUntil: 'domcontentloaded' })
    await settle(page, opts.timeout)
    const hrefs = await page
      .locator(`a[href^="${prefix}"]`)
      .evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).getAttribute('href') ?? ''))
    return hrefs.find((h) => h.length > prefix.length && !h.includes('?')) ?? null
  }
  const briefing =
    (await firstHref('/briefing', '/briefing/')) ?? (await firstHref('/dashboard', '/briefing/'))
  const paper = await firstHref('/papers', '/papers/')
  await ctx.close()
  const date = briefing?.split('/')[2] ?? null
  const id = paper?.split('/')[2] ?? null
  return { date, id }
}

function resolveRoute(
  route: string,
  params: { date: string | null; id: string | null },
): string | null {
  if (route.includes('[date]')) {
    if (!params.date) return null
    route = route.replace('[date]', params.date)
  }
  if (route.includes('[id]')) {
    if (!params.id) return null
    route = route.replace('[id]', params.id)
  }
  return PSEUDO_ROUTES[route] ?? route
}

function wanted(screen: Screen, opts: Options): boolean {
  if (!opts.routes) return true
  return opts.routes.some((r) => r === screen.route || r === screen.name)
}

// ---------------------------------------------------------------- main

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  const startedAt = new Date()
  log(
    `Screenshots → ${opts.url}  (${opts.viewports.join(', ')}; ${opts.fullPage ? 'full page' : 'viewport'}${
      opts.lang ? `; lang=${opts.lang}` : ''
    }${opts.theme === 'dark' ? '; dark' : ''})`,
  )
  log(`Output       → ${opts.out}`)

  const browser = await chromium.launch({ headless: !opts.headed })
  const shots: Shot[] = []
  let failed = false
  try {
    const cookies = await login(browser, opts)
    log(`Signed in as ${opts.user}`)
    const params = await discover(browser, opts, cookies)
    log(`Discovered   → briefing date=${params.date ?? '—'}  paper id=${params.id ?? '—'}`)

    for (const vpName of opts.viewports) {
      const viewport = VIEWPORTS[vpName]
      const dir = join(opts.out, vpName)
      await mkdir(dir, { recursive: true })
      log(
        `\n[${vpName}] ${viewport.width}×${viewport.height} @${opts.scale ?? viewport.deviceScaleFactor}x`,
      )

      for (const screen of SCREENS) {
        if (!wanted(screen, opts)) continue
        if (screen.only && !screen.only.includes(vpName)) continue
        // Number by position in SCREENS so the same screen keeps the same
        // filename across viewports, runs and --routes subsets (gaps are fine).
        const file = `${String(SCREENS.indexOf(screen) + 1).padStart(2, '0')}-${screen.name}.png`
        const shot: Shot = {
          name: screen.name,
          route: screen.route,
          url: '',
          viewport: vpName,
          file: null,
          status: null,
          finalUrl: null,
          error: null,
          overflowX: 0,
          truncated: false,
        }
        shots.push(shot)

        const path = resolveRoute(screen.route, params)
        if (!path) {
          shot.error = `no ${screen.route.includes('[date]') ? 'briefing edition' : 'paper'} link found to expand ${screen.route}`
          log(`  skip ${file.padEnd(28)} ${shot.error}`)
          continue
        }
        shot.url = opts.url + path

        const ctx = await newContext(browser, opts, viewport)
        if (screen.auth) await ctx.addCookies(cookies)
        const page = await ctx.newPage()
        try {
          const res = await page.goto(path, { waitUntil: 'domcontentloaded' })
          await settle(page, opts.timeout)
          shot.status = res?.status() ?? null
          shot.finalUrl = page.url()
          if (screen.auth && new URL(page.url()).pathname === '/') {
            throw new Error('redirected to the sign-in page (session rejected)')
          }
          if (screen.interact) await screen.interact(page)
          const target = join(dir, file)
          const fullPage = opts.fullPage && !screen.viewportOnly
          // Clip to the viewport width so a horizontally overflowing page does
          // not produce a 60,000px-wide image; report the overflow instead.
          const doc = await page.evaluate(() => ({
            width: document.documentElement.scrollWidth,
            height: document.documentElement.scrollHeight,
          }))
          shot.overflowX = Math.max(0, doc.width - viewport.width)
          const dsf = opts.scale ?? viewport.deviceScaleFactor
          const maxHeight = Math.floor(MAX_DEVICE_PX / dsf)
          const height = fullPage ? Math.min(doc.height, maxHeight) : viewport.height
          shot.truncated = fullPage && doc.height > maxHeight
          await page.screenshot({
            path: target,
            fullPage,
            clip: { x: 0, y: 0, width: viewport.width, height },
            animations: 'disabled',
            caret: 'hide',
          })
          shot.file = relative(opts.out, target)
          const flags: string[] = []
          if (shot.status && shot.status >= 400) flags.push(`⚠ HTTP ${shot.status}`)
          if (shot.overflowX) flags.push(`↔ overflows by ${shot.overflowX}px`)
          if (shot.truncated) flags.push(`✂ cut at ${height}px of ${doc.height}px`)
          log(`  ${file.padEnd(28)} ${path}${flags.length ? '  ' + flags.join('  ') : ''}`)
          if (shot.status && shot.status >= 400) failed = true
        } catch (err) {
          shot.error = (err as Error).message.split('\n')[0]
          failed = true
          log(`  FAIL ${file.padEnd(28)} ${path}: ${shot.error}`)
        } finally {
          await ctx.close()
        }
      }
    }
  } catch (err) {
    failed = true
    console.error(`\n${(err as Error).message}`)
  } finally {
    await browser.close()
  }

  if (shots.length === 0) {
    process.exit(2)
  }

  const manifest = {
    baseUrl: opts.url,
    capturedAt: startedAt.toISOString(),
    lang: opts.lang,
    theme: opts.theme,
    fullPage: opts.fullPage,
    viewports: Object.fromEntries(
      opts.viewports.map((v) => [
        v,
        { ...VIEWPORTS[v], deviceScaleFactor: opts.scale ?? VIEWPORTS[v].deviceScaleFactor },
      ]),
    ),
    shots,
  }
  await mkdir(opts.out, { recursive: true })
  await writeFile(join(opts.out, 'manifest.json'), JSON.stringify(manifest, null, 2))
  await writeFile(join(opts.out, 'index.html'), contactSheet(manifest))

  const screensRoot = resolve(import.meta.dir, '..', 'screenshots')
  const latest = join(screensRoot, 'latest')
  if (resolve(opts.out).startsWith(screensRoot + sep) && resolve(opts.out) !== latest) {
    // rm with force tolerates a missing or dangling symlink; it removes only
    // the link itself, never the directory it points to.
    await rm(latest, { recursive: true, force: true })
    await symlink(relative(screensRoot, resolve(opts.out)), latest)
  }

  const ok = shots.filter((s) => s.file && !s.error && !(s.status && s.status >= 400)).length
  log(`\n${ok}/${shots.length} screens captured → ${opts.out}`)
  log(`Contact sheet: ${join(opts.out, 'index.html')}`)
  process.exit(failed ? 1 : 0)
}

function contactSheet(manifest: {
  baseUrl: string
  capturedAt: string
  viewports: Record<string, Viewport>
  shots: Shot[]
}): string {
  const vps = Object.keys(manifest.viewports)
  const names = [...new Set(manifest.shots.map((s) => s.name))]
  const esc = (s: string) =>
    s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] ?? c)
  const cell = (shot: Shot | undefined) => {
    if (!shot) return '<td class="na">—</td>'
    if (!shot.file) return `<td class="na">${esc(shot.error ?? 'not captured')}</td>`
    const notes: string[] = []
    if (shot.error) notes.push(shot.error)
    else if (shot.status && shot.status >= 400) notes.push(`HTTP ${shot.status}`)
    if (shot.overflowX) notes.push(`overflows viewport by ${shot.overflowX}px`)
    if (shot.truncated) notes.push('cut at capture limit')
    const warn = notes.length ? ` <b class="warn">${esc(notes.join(' · '))}</b>` : ''
    return `<td><a href="${esc(shot.file)}" target="_blank"><img src="${esc(shot.file)}" loading="lazy"></a><div class="meta">${esc(shot.file)}${warn}</div></td>`
  }
  const rows = names
    .map((name) => {
      const first = manifest.shots.find((s) => s.name === name)!
      const cells = vps
        .map((v) => cell(manifest.shots.find((s) => s.name === name && s.viewport === v)))
        .join('')
      return `<tr><th><div>${esc(name)}</div><code>${esc(first.route)}</code></th>${cells}</tr>`
    })
    .join('\n')
  const cols = vps
    .map(
      (v) =>
        `<th>${esc(v)} <small>${manifest.viewports[v].width}×${manifest.viewports[v].height}</small></th>`,
    )
    .join('')
  return `<!doctype html><meta charset="utf-8"><title>Screens ${esc(manifest.capturedAt)}</title>
<style>
body{font:14px/1.4 system-ui,sans-serif;margin:24px;color:#222;background:#f4f4f2}
h1{font-size:18px;margin:0 0 4px}p{margin:0 0 16px;color:#666}
table{border-collapse:separate;border-spacing:12px;width:100%}
th{text-align:left;vertical-align:top;font-weight:600;white-space:nowrap}th code{font-weight:400;color:#666}
td{vertical-align:top;background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px}
td img{display:block;max-width:100%;max-height:70vh;object-fit:contain;object-position:top;border:1px solid #eee}
.meta{margin-top:6px;color:#666;font-size:12px;word-break:break-all}.warn{color:#b00}.na{color:#999}
</style>
<h1>${esc(manifest.baseUrl)}</h1><p>${esc(manifest.capturedAt)} · click an image for full size</p>
<table><tr><th></th>${cols}</tr>
${rows}
</table>`
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err)
  process.exit(2)
})

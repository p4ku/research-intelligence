#!/usr/bin/env bun
/**
 * Walk a persona journey through the running app and capture it twice over:
 * a still per step (`NN-<slug>.png`) and, for the steps marked `clip: true`,
 * a short screen recording (`NN-<slug>.mp4` + `-poster.png`) cut out of one
 * continuous video of the whole run.
 *
 * The journey definitions live in `docs/journeys/journeys.json` — that file is
 * the source of truth for what a persona does, in order. This script only
 * performs it: one browser context per consecutive block of steps sharing a
 * `capture.target` (`replay` = the local snapshot server, `prod` = production,
 * used where the replay refuses writes), 1440x900, light, en-GB, Europe/Berlin.
 * Motion is deliberately NOT reduced — the clips exist to show the transitions
 * `scripts/lib/browser.ts` switches off for still screenshots.
 *
 * The pace is intentional: every click is preceded by a ring drawn round its
 * target, and every step ends with a beat of stillness before the shutter, so
 * the clips are watchable rather than a blur.
 *
 *   bun run journeys                                   # the "executive" journey needs --journey
 *   bun run journeys --journey executive               # replay at http://localhost:3009
 *   bun run journeys --journey analyst --steps 1-4     # re-run part of a journey
 *   bun run journeys --journey expert --headed         # watch it happen
 *   bun run journeys --journey executive --workspace "Hybrid Computing"
 *
 * NOTE ON `--steps`: each invocation starts from a blank browser, and no state
 * carries over from a previous one. A subset must therefore begin with a step
 * whose actions establish its own state — a `goto`, or a `login` — or it will
 * open on a blank page and fail on its first selector.
 *
 * Needs a running app (`bun run dev` against the replay or a real backend — see
 * local-docs/snapshot-replay.md) and ffmpeg for the clips. Any credentials work
 * against the replay; a real backend needs $SCREENSHOT_PASSWORD.
 *
 * Writes `<out>/<journey>/manifest.json` and folds the same paths back into the
 * matching journey in the spec file (only the generated `capture` fields), so
 * the walkthrough page can be built straight from the spec.
 */
import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, relative, resolve } from 'node:path'
import { promisify } from 'node:util'
import { chromium, type Browser, type Locator, type Page } from 'playwright'
import { settle, VIEWPORTS } from './lib/browser'

const run = promisify(execFile)

const FFMPEG = process.env.FFMPEG ?? '/opt/homebrew/bin/ffmpeg'
/** Beat of stillness before a click lands and before the shutter. */
const HOLD_MS = 1_000
/** Longest clip we cut; anything longer keeps its last TRIM_TO_S seconds. */
const MAX_CLIP_S = 25
const TRIM_TO_S = 20
/** Padding either side of a step's window, so the cut does not clip a transition. */
const PAD_S = 0.5

// ---------------------------------------------------------------- spec shape

type Target = 'replay' | 'prod'

interface ClickAction {
  selector?: string
  role?: string
  name?: string
}
interface FillAction {
  selector: string
  value: string
}
interface ScrollAction {
  selector?: string
  text?: string
}
interface PressAction {
  selector?: string
  key: string
}

/** The whole action vocabulary; a step's `actions` are objects with one key each. */
interface Action {
  goto?: string
  login?: boolean
  click?: ClickAction
  fill?: FillAction
  press?: string | PressAction
  waitForSelector?: string
  waitForText?: string
  waitForUrl?: string
  scrollTo?: ScrollAction
  hold?: number
}

interface Capture {
  target: Target
  fullPage?: boolean
  clip?: boolean
  /**
   * Crop the still to a rectangle of the viewport (CSS pixels, page
   * coordinates), for screens where a fixed rail or a stretched panel puts
   * dead space in a frame the step is not about. Ignored when `fullPage`.
   */
  region?: { x: number; y: number; width: number; height: number } | null
  actions: Action[]
  // Filled in by this script.
  file?: string | null
  video?: string | null
  poster?: string | null
  url?: string | null
  status?: number | null
  capturedAt?: string | null
  clipRange?: [number, number] | null
}

interface Step {
  n: number
  slug: string
  route?: string
  title?: string
  capture: Capture
}

interface Journey {
  id: string
  steps: Step[]
}

interface Spec {
  baseUrl?: string
  prodUrl?: string
  workspace?: { id?: string; name?: string }
  viewport?: { width: number; height: number; deviceScaleFactor?: number }
  journeys: Journey[]
}

// ---------------------------------------------------------------- arguments

interface Options {
  spec: string
  journey: string | null
  url: string | null
  out: string | null
  workspace: string | null
  steps: number[] | null
  headed: boolean
  user: string
  password: string
  timeout: number
}

/** `frontend/` — the directory `bun run journeys` is invoked from. */
const APP_DIR = resolve(import.meta.dir, '..')

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    spec: join(APP_DIR, '..', 'docs', 'journeys', 'journeys.json'),
    journey: null,
    url: process.env.SCREENSHOT_URL ?? null,
    out: null,
    workspace: null,
    steps: null,
    headed: false,
    user: process.env.SCREENSHOT_USER ?? 'admin',
    // The replay server accepts any password; a real backend needs the real one
    // via $SCREENSHOT_PASSWORD (see local-docs/backend-frontend-seam.md).
    password: process.env.SCREENSHOT_PASSWORD ?? 'replay',
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
      case '--spec':
        opts.spec = resolve(next(i++, a))
        break
      case '--journey':
        opts.journey = next(i++, a)
        break
      case '--url':
        opts.url = next(i++, a)
        break
      case '--out':
        opts.out = resolve(next(i++, a))
        break
      case '--workspace':
        opts.workspace = next(i++, a)
        break
      case '--steps':
        opts.steps = parseSteps(next(i++, a))
        break
      case '--user':
        opts.user = next(i++, a)
        break
      case '--password':
        opts.password = next(i++, a)
        break
      case '--timeout':
        opts.timeout = Number(next(i++, a))
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
  if (!opts.journey) throw new Error(`--journey is required\n${usage()}`)
  if (opts.url) opts.url = opts.url.replace(/\/+$/, '')
  if (!Number.isFinite(opts.timeout) || opts.timeout <= 0)
    throw new Error('--timeout must be a positive number of milliseconds')
  return opts
}

/** `4-6`, `2`, `1,3,7` or any mix of those. */
function parseSteps(raw: string): number[] {
  const out = new Set<number>()
  for (const part of raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)) {
    const range = /^(\d+)\s*-\s*(\d+)$/.exec(part)
    if (range) {
      const from = Number(range[1])
      const to = Number(range[2])
      if (to < from) throw new Error(`--steps range "${part}" runs backwards`)
      for (let n = from; n <= to; n++) out.add(n)
      continue
    }
    if (!/^\d+$/.test(part)) throw new Error(`--steps expects numbers or ranges, got "${part}"`)
    out.add(Number(part))
  }
  if (!out.size) throw new Error('--steps matched nothing')
  return [...out].sort((a, b) => a - b)
}

function usage(): string {
  return `Usage: bun run journeys --journey <id> [options]
  --spec <path>           journey definitions (default ../docs/journeys/journeys.json)
  --journey <id>          which journey to walk (required)
  --url <origin>          override the replay origin (default the spec's baseUrl)
  --out <dir>             output root (default ../docs/journeys/shots)
  --workspace <id|name>   workspace to pin (default the spec's; a name is resolved by lookup)
  --steps <list>          only these step numbers, e.g. 4-6 or 1,3 (must start with goto/login)
  --user/--password       login (default admin / $SCREENSHOT_PASSWORD; anything works on the replay)
  --headed                show the browser
  --timeout <ms>          per-action timeout (default 30000)`
}

// ---------------------------------------------------------------- helpers

interface ShotRecord {
  n: number
  slug: string
  file: string | null
  video: string | null
  poster: string | null
  url: string | null
  status: number | null
  clipRange: [number, number] | null
  error: string | null
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function log(msg: string) {
  console.log(msg)
}

function round(seconds: number): number {
  return Math.round(seconds * 100) / 100
}

/** The single action key on an action object, for error messages. */
function actionName(action: Action): string {
  return Object.keys(action)[0] ?? '(empty)'
}

function locate(page: Page, target: ClickAction | ScrollAction | PressAction): Locator {
  if ('selector' in target && target.selector) return page.locator(target.selector).first()
  if ('role' in target && target.role) {
    if (!target.name) throw new Error('role needs a matching name')
    return page
      .getByRole(target.role as Parameters<Page['getByRole']>[0], { name: target.name })
      .first()
  }
  if ('text' in target && target.text) return page.getByText(target.text).first()
  throw new Error('needs a selector, a role + name, or a text')
}

/**
 * Draw a ring round what is about to be clicked and leave it up for about a
 * second, so a viewer of the clip sees the target before the page changes.
 */
async function ring(page: Page, box: { x: number; y: number; width: number; height: number }) {
  await page.evaluate((b) => {
    const accent =
      getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#00c3cd'
    const el = document.createElement('div')
    el.setAttribute('data-journey-ring', '')
    el.style.cssText = [
      'position:fixed',
      `left:${b.x - 5}px`,
      `top:${b.y - 5}px`,
      `width:${b.width + 10}px`,
      `height:${b.height + 10}px`,
      `border:2px solid ${accent}`,
      'border-radius:10px',
      `box-shadow:0 0 0 4px ${accent}33`,
      'pointer-events:none',
      'z-index:2147483647',
      'opacity:0',
      'transition:opacity 180ms ease',
    ].join(';')
    document.body.appendChild(el)
    requestAnimationFrame(() => {
      el.style.opacity = '1'
    })
    setTimeout(() => {
      el.style.opacity = '0'
      setTimeout(() => el.remove(), 220)
    }, 780)
  }, box)
  await page.waitForTimeout(HOLD_MS)
}

// ---------------------------------------------------------------- the walk

interface RunContext {
  page: Page
  base: string
  opts: Options
  /** Set once the run has signed in, so the workspace cookie is applied once. */
  workspacePinned: boolean
  workspaceId: string | null
  workspaceLabel: string
}

/** Sign in through the real form, then pin the workspace before anything else. */
async function doLogin(rc: RunContext) {
  const { page, opts } = rc
  const identifier = page.locator("input[name='identifier']")
  if ((await identifier.count()) === 0) {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await settle(page, opts.timeout)
  }
  try {
    await identifier.fill(opts.user)
    await page.locator("input[name='password']").fill(opts.password)
    await page.locator("button[type='submit']").click()
    await page.waitForURL((u) => u.pathname !== '/', { timeout: opts.timeout })
    await settle(page, opts.timeout)
  } catch (err) {
    const alert = await page
      .locator("[role='alert']")
      .first()
      .textContent({ timeout: 1_000 })
      .catch(() => null)
    throw new Error(
      `sign-in failed at ${rc.base} as ${opts.user}: ${alert?.trim() || (err as Error).message}` +
        ' (against a real backend set SCREENSHOT_PASSWORD — see local-docs/backend-frontend-seam.md;' +
        ' the replay accepts any password)',
    )
  }
  const cookies = await page.context().cookies()
  if (!cookies.some((c) => c.name === 'sri_access')) {
    throw new Error(`sign-in produced no session at ${rc.base}`)
  }
  // Sign-in may hand back its own workspace cookie; ours has to win.
  await pinWorkspace(rc, true)
}

/**
 * The workspace list opens on whichever workspace sorts first, which is rarely
 * the one a journey is about. Resolve a name to its id if needed, set the
 * cookie, and reload so the page in view is already the right workspace.
 */
async function pinWorkspace(rc: RunContext, force = false) {
  if (!rc.workspaceId || (rc.workspacePinned && !force)) return
  const { page } = rc
  const session = await page.context().cookies()
  // Before sign-in there is nothing to scope and no way to resolve a name;
  // the login action pins it the moment there is a session.
  if (!session.some((c) => c.name === 'sri_access')) return
  if (!UUID.test(rc.workspaceId)) {
    const wanted = rc.workspaceId
    const res = await page.context().request.get(`${rc.base}/bff/workspaces?page_size=200`)
    if (!res.ok()) {
      throw new Error(`could not list workspaces to resolve "${wanted}" (HTTP ${res.status()})`)
    }
    const body = (await res.json()) as { results?: { id: string; name: string }[] }
    const match = (body.results ?? []).find(
      (w) => w.name.toLowerCase() === wanted.toLowerCase() || w.id === wanted,
    )
    if (!match) {
      const names = (body.results ?? []).map((w) => w.name).join(', ')
      throw new Error(
        `no workspace named "${wanted}" at ${rc.base} (available: ${names || 'none'})`,
      )
    }
    rc.workspaceId = match.id
    rc.workspaceLabel = match.name
  }
  await page.context().addCookies([{ name: 'rs-workspace', value: rc.workspaceId, url: rc.base }])
  rc.workspacePinned = true
  // Anything already rendered is showing the default workspace; re-fetch it.
  if (!page.url().startsWith('about:')) {
    await page.reload({ waitUntil: 'domcontentloaded' })
    await settle(page, rc.opts.timeout)
  }
}

async function perform(rc: RunContext, action: Action) {
  const { page, opts } = rc
  if (action.goto !== undefined) {
    await pinWorkspace(rc)
    await page.goto(action.goto, { waitUntil: 'domcontentloaded' })
    await settle(page, opts.timeout)
    return
  }
  if (action.login) {
    await doLogin(rc)
    return
  }
  if (action.click) {
    const locator = locate(page, action.click)
    await locator.waitFor({ state: 'visible', timeout: opts.timeout })
    await locator.scrollIntoViewIfNeeded()
    const box = await locator.boundingBox()
    if (box) await ring(page, box)
    await locator.click()
    await settle(page, opts.timeout)
    await page.waitForTimeout(HOLD_MS)
    return
  }
  if (action.fill) {
    const locator = page.locator(action.fill.selector).first()
    await locator.waitFor({ state: 'visible', timeout: opts.timeout })
    await locator.click()
    // Type it rather than set it, so the clip shows the field filling.
    await locator.fill('')
    if (action.fill.value) await locator.pressSequentially(action.fill.value, { delay: 18 })
    return
  }
  if (action.press !== undefined) {
    const press = typeof action.press === 'string' ? { key: action.press } : action.press
    if (press.selector) await page.locator(press.selector).first().press(press.key)
    else await page.keyboard.press(press.key)
    await settle(page, opts.timeout)
    return
  }
  if (action.waitForSelector !== undefined) {
    await page
      .locator(action.waitForSelector)
      .first()
      .waitFor({ state: 'visible', timeout: opts.timeout })
    return
  }
  if (action.waitForText !== undefined) {
    await page
      .getByText(action.waitForText)
      .first()
      .waitFor({ state: 'visible', timeout: opts.timeout })
    return
  }
  if (action.waitForUrl !== undefined) {
    const wanted = action.waitForUrl
    await page.waitForURL((u) => u.href.includes(wanted) || u.pathname.includes(wanted), {
      timeout: opts.timeout,
    })
    await settle(page, opts.timeout)
    return
  }
  if (action.scrollTo) {
    const locator = locate(page, action.scrollTo)
    await locator.waitFor({ state: 'visible', timeout: opts.timeout })
    await locator.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }))
    await page.waitForTimeout(900)
    return
  }
  if (action.hold !== undefined) {
    await page.waitForTimeout(action.hold)
    return
  }
  throw new Error(`unknown action ${JSON.stringify(action)}`)
}

// ---------------------------------------------------------------- clipping

/** Cut one step's window out of the run's video and grab its first frame. */
async function cutClip(
  source: string,
  from: number,
  to: number,
  mp4: string,
  poster: string,
): Promise<{ range: [number, number]; trimmed: boolean }> {
  let start = Math.max(0, from - PAD_S)
  const end = to + PAD_S
  let trimmed = false
  if (end - start > MAX_CLIP_S) {
    start = Math.max(0, end - TRIM_TO_S)
    trimmed = true
  }
  await run(FFMPEG, [
    '-y',
    '-ss',
    String(round(start)),
    '-to',
    String(round(end)),
    '-i',
    source,
    '-c:v',
    'libx264',
    '-crf',
    '23',
    '-pix_fmt',
    'yuv420p',
    '-r',
    '25',
    '-movflags',
    '+faststart',
    '-an',
    mp4,
  ])
  await run(FFMPEG, ['-y', '-i', mp4, '-frames:v', '1', poster])
  return { range: [round(start), round(end)], trimmed }
}

// ---------------------------------------------------------------- main

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  const specRaw = await readFile(opts.spec, 'utf8').catch(() => {
    throw new Error(`cannot read the journey spec at ${opts.spec}`)
  })
  const spec = JSON.parse(specRaw) as Spec
  const journey = spec.journeys?.find((j) => j.id === opts.journey)
  if (!journey) {
    throw new Error(
      `no journey "${opts.journey}" in ${opts.spec} (have: ${(spec.journeys ?? []).map((j) => j.id).join(', ')})`,
    )
  }

  const replayUrl = (opts.url ?? spec.baseUrl ?? 'http://localhost:3009').replace(/\/+$/, '')
  const prodUrl = (spec.prodUrl ?? '').replace(/\/+$/, '')
  const out = opts.out ?? join(APP_DIR, '..', 'docs', 'journeys', 'shots')
  const dir = join(out, journey.id)
  const viewport = {
    width: spec.viewport?.width ?? VIEWPORTS.desktop.width,
    height: spec.viewport?.height ?? VIEWPORTS.desktop.height,
    deviceScaleFactor: spec.viewport?.deviceScaleFactor ?? VIEWPORTS.desktop.deviceScaleFactor,
  }
  const workspaceWanted = opts.workspace ?? spec.workspace?.id ?? spec.workspace?.name ?? null

  const steps = opts.steps ? journey.steps.filter((s) => opts.steps!.includes(s.n)) : journey.steps
  if (!steps.length) {
    throw new Error(`--steps matched no step of "${journey.id}" (it has ${journey.steps.length})`)
  }
  if (steps.some((s) => s.capture.target === 'prod') && !prodUrl) {
    throw new Error('the journey has steps targeting prod but the spec has no prodUrl')
  }

  await mkdir(dir, { recursive: true })
  const videoRoot = await mkdtemp(join(tmpdir(), 'journey-video-'))
  const startedAt = new Date()

  log(`Journey  → ${journey.id}  (${steps.length} step${steps.length === 1 ? '' : 's'})`)
  log(`Replay   → ${replayUrl}`)
  if (steps.some((s) => s.capture.target === 'prod')) log(`Prod     → ${prodUrl}`)
  log(`Output   → ${dir}`)

  // One context per consecutive block of steps sharing a target: state has to
  // carry from step to step, but the two targets are different origins.
  const runs: { target: Target; steps: Step[] }[] = []
  for (const step of steps) {
    const last = runs[runs.length - 1]
    if (last && last.target === step.capture.target) last.steps.push(step)
    else runs.push({ target: step.capture.target, steps: [step] })
  }

  const records: ShotRecord[] = []
  const browser: Browser = await chromium.launch({ headless: !opts.headed })
  let failed = false
  let workspaceLabel = spec.workspace?.name ?? workspaceWanted ?? ''

  try {
    for (const [index, group] of runs.entries()) {
      const base = group.target === 'prod' ? prodUrl : replayUrl
      const videoDir = join(videoRoot, String(index))
      const ctx = await browser.newContext({
        baseURL: base,
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: viewport.deviceScaleFactor,
        // No reducedMotion here on purpose: the clips are about the transitions.
        colorScheme: 'light',
        locale: 'en-GB',
        timezoneId: 'Europe/Berlin',
        recordVideo: { dir: videoDir, size: { width: viewport.width, height: viewport.height } },
      })
      ctx.setDefaultTimeout(opts.timeout)
      // Keep the dev-server badge out of the recording as well as the stills.
      await ctx.addInitScript(() => {
        const add = () => {
          const style = document.createElement('style')
          style.textContent = 'nextjs-portal{display:none!important}'
          document.head?.appendChild(style)
        }
        if (document.head) add()
        else document.addEventListener('DOMContentLoaded', add)
      })

      const page = await ctx.newPage()
      const t0 = Date.now()
      const elapsed = () => (Date.now() - t0) / 1_000
      let status: number | null = null
      page.on('response', (res) => {
        const req = res.request()
        if (req.resourceType() === 'document' && req.frame() === page.mainFrame()) {
          status = res.status()
        }
      })

      const rc: RunContext = {
        page,
        base,
        opts,
        workspacePinned: false,
        workspaceId: workspaceWanted,
        workspaceLabel,
      }

      const windows = new Map<number, [number, number]>()
      let aborted = false
      for (const step of group.steps) {
        const name = `${String(step.n).padStart(2, '0')}-${step.slug}`
        const record: ShotRecord = {
          n: step.n,
          slug: step.slug,
          file: null,
          video: null,
          poster: null,
          url: null,
          status: null,
          clipRange: null,
          error: null,
        }
        records.push(record)
        if (aborted) {
          record.error = 'skipped after an earlier step failed'
          log(`  skip ${name.padEnd(28)} ${record.error}`)
          continue
        }
        const from = elapsed()
        try {
          for (const action of step.capture.actions ?? []) {
            try {
              await perform(rc, action)
            } catch (err) {
              throw new Error(
                `action "${actionName(action)}" — ${(err as Error).message.split('\n')[0]}`,
              )
            }
          }
          await settle(page, opts.timeout)
          await page.waitForTimeout(HOLD_MS)
          const file = `${name}.png`
          const region = step.capture.fullPage === true ? null : (step.capture.region ?? null)
          await page.screenshot({
            path: join(dir, file),
            fullPage: step.capture.fullPage === true,
            ...(region ? { clip: region } : {}),
            caret: 'hide',
          })
          record.file = file
          record.url = page.url()
          record.status = status
          if (step.capture.clip) windows.set(step.n, [from, elapsed()])
          const flag = status && status >= 400 ? `  ⚠ HTTP ${status}` : ''
          if (status && status >= 400) failed = true
          log(`  ${name.padEnd(28)} ${record.url}${flag}`)
        } catch (err) {
          record.error = `step ${step.n} (${step.slug}): ${(err as Error).message.split('\n')[0]}`
          record.url = page.url()
          record.status = status
          failed = true
          aborted = true
          log(`  FAIL ${name.padEnd(28)} ${record.error}`)
        }
      }
      workspaceLabel = rc.workspaceLabel

      const video = page.video()
      await ctx.close()
      const source = video ? await video.path() : null
      if (source && windows.size) {
        for (const [n, [from, to]] of windows) {
          const step = group.steps.find((s) => s.n === n)!
          const record = records.find((r) => r.n === n)!
          const name = `${String(step.n).padStart(2, '0')}-${step.slug}`
          try {
            const { range, trimmed } = await cutClip(
              source,
              from,
              to,
              join(dir, `${name}.mp4`),
              join(dir, `${name}-poster.png`),
            )
            record.video = `${name}.mp4`
            record.poster = `${name}-poster.png`
            record.clipRange = range
            log(
              `  clip ${name.padEnd(28)} ${range[0]}s–${range[1]}s${trimmed ? `  (trimmed to the last ${TRIM_TO_S}s)` : ''}`,
            )
          } catch (err) {
            record.error = `step ${n}: clip failed — ${(err as Error).message.split('\n')[0]}`
            failed = true
            log(`  FAIL clip ${name.padEnd(23)} ${record.error}`)
          }
        }
      }
    }
  } catch (err) {
    failed = true
    console.error(`\n${(err as Error).message}`)
  } finally {
    await browser.close()
    await rm(videoRoot, { recursive: true, force: true })
  }

  const capturedAt = startedAt.toISOString()
  const manifest = {
    journey: journey.id,
    baseUrls: {
      replay: replayUrl,
      ...(steps.some((s) => s.capture.target === 'prod') ? { prod: prodUrl } : {}),
    },
    workspace: { id: workspaceWanted, name: workspaceLabel || null },
    capturedAt,
    steps: records,
  }
  await writeFile(join(dir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')

  // Fold the generated paths back into the spec, relative to the spec itself.
  const rel = (file: string | null) => (file ? relative(dirname(opts.spec), join(dir, file)) : null)
  for (const record of records) {
    const step = journey.steps.find((s) => s.n === record.n)
    if (!step) continue
    step.capture.file = rel(record.file)
    step.capture.video = rel(record.video)
    step.capture.poster = rel(record.poster)
    step.capture.url = record.url
    step.capture.status = record.status
    step.capture.capturedAt = record.file ? capturedAt : null
    step.capture.clipRange = record.clipRange
  }
  await writeFile(opts.spec, JSON.stringify(spec, null, 2) + '\n')

  const ok = records.filter((r) => r.file && !r.error).length
  log(`\n${ok}/${records.length} steps captured → ${dir}`)
  process.exit(failed ? 1 : 0)
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err)
  process.exit(2)
})

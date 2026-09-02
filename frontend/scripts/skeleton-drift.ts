#!/usr/bin/env bun
/**
 * Skeleton drift check: opens /studio/skeletons?motion=static (the gallery of
 * loaded/skeleton pairs) and measures every `[data-pair]` — the root
 * `[data-shape]` box and each `[data-row]` inside it, in both panes. A
 * skeleton that has drifted from its component (extra row, different height)
 * fails the run. Keeps `FooSkeleton` honest without a runtime dependency.
 *
 *   bun run skeleton:drift                       # desktop gates; needs a running app
 *   bun run skeleton:drift --url http://localhost:3006
 *   bun run skeleton:drift --viewports desktop,mobile   # mobile is report-only
 *   bun run skeleton:drift --stream /dashboard   # also assert the fallback streams first
 *   bun run skeleton:drift --not-found /papers/00000000-0000-4000-8000-0000000000ff
 *                                                # a dead permalink on a route with loading.tsx:
 *                                                # HTTP 200 with the not-found page in-stream
 *
 * Env: SCREENSHOT_URL, SCREENSHOT_USER, SCREENSHOT_PASSWORD (shared with
 * scripts/screenshots.ts; any password works against the replay server).
 */
import { chromium } from 'playwright'
import { login, newContext, settle, VIEWPORTS, type BrowserOptions } from './lib/browser'

interface Options extends BrowserOptions {
  viewports: string[]
  tolerance: number
  stream: string | null
  notFound: string | null
  headed: boolean
}

interface Rect {
  width: number
  height: number
}

interface Pane {
  rect: Rect
  rows: { row: string; rect: Rect }[]
}

interface PairMeasure {
  name: string
  loaded: Pane | null
  skeleton: Pane | null
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    url: process.env.SCREENSHOT_URL ?? 'http://localhost:3009',
    user: process.env.SCREENSHOT_USER ?? 'admin',
    password: process.env.SCREENSHOT_PASSWORD ?? 'replay',
    lang: null,
    theme: 'light',
    scale: null,
    timeout: 30_000,
    viewports: ['desktop'],
    tolerance: 4,
    stream: null,
    notFound: null,
    headed: false,
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
        opts.url = next(i++, a).replace(/\/+$/, '')
        break
      case '--user':
        opts.user = next(i++, a)
        break
      case '--password':
        opts.password = next(i++, a)
        break
      case '--viewports':
        opts.viewports = next(i++, a)
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        break
      case '--tolerance':
        opts.tolerance = Number(next(i++, a))
        break
      case '--timeout':
        opts.timeout = Number(next(i++, a))
        break
      case '--stream':
        opts.stream = next(i++, a)
        break
      case '--not-found':
        opts.notFound = next(i++, a)
        break
      case '--headed':
        opts.headed = true
        break
      default:
        throw new Error(`Unknown argument ${a}`)
    }
  }
  for (const v of opts.viewports) {
    if (!(v in VIEWPORTS))
      throw new Error(`Unknown viewport "${v}" (${Object.keys(VIEWPORTS).join(', ')})`)
  }
  if (!Number.isFinite(opts.tolerance) || opts.tolerance < 0)
    throw new Error('--tolerance must be a non-negative number of px')
  return opts
}

/** Measure every gallery pair inside the page. Runs in the browser. */
function measurePairs(): PairMeasure[] {
  const rect = (el: Element): Rect => {
    const r = el.getBoundingClientRect()
    return { width: r.width, height: r.height }
  }
  return [...document.querySelectorAll('[data-pair]')].map((pair) => {
    const pane = (which: string): Pane | null => {
      const holder = pair.querySelector(`[data-pane="${which}"]`)
      const root = holder?.querySelector('[data-shape]')
      if (!root) return null
      return {
        rect: rect(root),
        rows: [...root.querySelectorAll('[data-row]')].map((r) => ({
          row: r.getAttribute('data-row') ?? '',
          rect: rect(r),
        })),
      }
    }
    return {
      name: pair.getAttribute('data-pair') ?? '?',
      loaded: pane('loaded'),
      skeleton: pane('skeleton'),
    }
  })
}

interface Finding {
  pair: string
  what: string
  delta: string
}

function compare(pairs: PairMeasure[], tolerance: number): Finding[] {
  const findings: Finding[] = []
  const px = (n: number) => `${Math.round(n * 10) / 10}px`
  for (const p of pairs) {
    const { loaded, skeleton } = p
    if (!loaded || !skeleton) {
      findings.push({ pair: p.name, what: 'pane missing', delta: loaded ? 'skeleton' : 'loaded' })
      continue
    }
    const dh = Math.abs(loaded.rect.height - skeleton.rect.height)
    const dw = Math.abs(loaded.rect.width - skeleton.rect.width)
    if (dh > tolerance || dw > tolerance) {
      findings.push({
        pair: p.name,
        what: 'root box',
        delta: `Δh ${px(dh)} Δw ${px(dw)} (loaded ${px(loaded.rect.height)} vs skeleton ${px(skeleton.rect.height)})`,
      })
    }
    if (loaded.rows.length !== skeleton.rows.length) {
      findings.push({
        pair: p.name,
        what: 'row count',
        delta: `loaded ${loaded.rows.length} vs skeleton ${skeleton.rows.length}`,
      })
      continue
    }
    loaded.rows.forEach((row, i) => {
      const other = skeleton.rows[i]
      const rdh = Math.abs(row.rect.height - other.rect.height)
      const rdw = Math.abs(row.rect.width - other.rect.width)
      if (rdh > tolerance || rdw > tolerance) {
        findings.push({
          pair: p.name,
          what: `row ${i} [${row.row}]`,
          delta: `Δh ${px(rdh)} Δw ${px(rdw)}`,
        })
      }
    })
  }
  return findings
}

/**
 * Assert the streamed HTML of `path` carries a Suspense fallback before any
 * boundary completion: the first `data-skeleton` byte must arrive before the
 * first `$RC(` — React's completion call, which swaps a resolved boundary in.
 * (`<template id="B:…">` is the *pending* boundary placeholder that sits with
 * the fallback, so it is not a completion marker.)
 */
async function checkStream(
  opts: Options,
  cookies: Awaited<ReturnType<typeof login>>,
  path: string,
): Promise<boolean> {
  const cookie = cookies.map((c) => `${c.name}=${c.value}`).join('; ')
  const started = performance.now()
  const res = await fetch(opts.url + path, { headers: { cookie } })
  if (!res.ok || !res.body) {
    console.error(`stream: GET ${path} → HTTP ${res.status}`)
    return false
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let firstChunkAt: number | null = null
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (firstChunkAt === null) firstChunkAt = performance.now() - started
    buffer += decoder.decode(value, { stream: true })
  }
  // Compare byte positions, not arrival times: a fast local server delivers
  // several boundaries in one chunk, which makes wall-clock timing useless,
  // while the order within the document is exactly the guarantee we want.
  const skeletonAt = buffer.indexOf('data-skeleton')
  const completionAt = buffer.indexOf('$RC(')
  const at = (n: number) => (n === -1 ? '—' : `byte ${n}`)
  const ok = skeletonAt !== -1 && (completionAt === -1 || skeletonAt < completionAt)
  console.log(
    `stream ${path}: first chunk at ${firstChunkAt === null ? '—' : `${Math.round(firstChunkAt)}ms`}, ` +
      `fallback at ${at(skeletonAt)}, first boundary completion at ${at(completionAt)} → ${ok ? 'OK' : 'FAIL'}`,
  )
  if (skeletonAt === -1) {
    console.error('stream: no data-skeleton in the response — the page is not streaming a fallback')
  }
  return ok
}

/**
 * Pin the documented trade of a loading.tsx on a dynamic segment: a dead id
 * streams the shell with HTTP 200 and renders the segment's not-found page
 * in place (docs/skeletons.md, pass 2). Asserts the status and the not-found
 * copy; reports whether Next added the noindex robots meta as well.
 */
async function checkNotFound(
  opts: Options,
  cookies: Awaited<ReturnType<typeof login>>,
  path: string,
): Promise<boolean> {
  const cookie = cookies.map((c) => `${c.name}=${c.value}`).join('; ')
  const res = await fetch(opts.url + path, { headers: { cookie } })
  const body = await res.text()
  // React escapes the apostrophe in the streamed HTML.
  const copy =
    body.includes('We couldn&#x27;t find that.') || body.includes("We couldn't find that.")
  const noindex = /<meta name="robots" content="noindex/.test(body)
  const ok = res.status === 200 && copy
  console.log(
    `not-found ${path}: HTTP ${res.status}, not-found copy ${copy ? 'present' : 'missing'}, ` +
      `noindex ${noindex ? 'present' : 'absent'} → ${ok ? 'OK' : 'FAIL'}`,
  )
  return ok
}

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  const browser = await chromium.launch({ headless: !opts.headed })
  let failed = false
  try {
    const cookies = await login(browser, opts)
    for (const vpName of opts.viewports) {
      const gate = vpName === 'desktop' // mobile is report-only: fixtures wrap at 390px
      const ctx = await newContext(browser, opts, VIEWPORTS[vpName])
      await ctx.addCookies(cookies)
      const page = await ctx.newPage()
      await page.goto('/studio/skeletons?motion=static', { waitUntil: 'domcontentloaded' })
      await settle(page, opts.timeout)
      const pairs = await page.evaluate(measurePairs)
      await ctx.close()
      if (pairs.length === 0) {
        console.error(`[${vpName}] no [data-pair] sections found on /studio/skeletons`)
        failed = true
        continue
      }
      const findings = compare(pairs, opts.tolerance)
      console.log(
        `[${vpName}] ${pairs.length} pairs, tolerance ${opts.tolerance}px → ${
          findings.length === 0 ? 'all within tolerance' : `${findings.length} finding(s)`
        }${gate ? '' : ' (report-only)'}`,
      )
      for (const f of findings) {
        console.log(`  ${gate ? 'FAIL' : 'note'} ${f.pair} · ${f.what} · ${f.delta}`)
      }
      if (gate && findings.length > 0) failed = true
    }
    if (opts.stream) {
      if (!(await checkStream(opts, cookies, opts.stream))) failed = true
    }
    if (opts.notFound) {
      if (!(await checkNotFound(opts, cookies, opts.notFound))) failed = true
    }
  } catch (err) {
    console.error((err as Error).message)
    failed = true
  } finally {
    await browser.close()
  }
  process.exit(failed ? 1 : 0)
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err)
  process.exit(2)
})

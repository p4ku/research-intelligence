'use client'

import { bffFetch } from '@/lib/bff/client'
import type { Palette, PaletteEntry } from '@/lib/bff/papers/schema'
import { useEffect, useRef, useState } from 'react'

/**
 * The picker's rows for what the reader has typed, fetched after the
 * console has painted.
 *
 * Nothing on the empty canvas needs a paper until the reader reaches for
 * one, so the rows are not worth a single blocked frame: the composer
 * renders at once and the empty-query palette follows in the first idle
 * moment. From then on this is a typeahead with the manners of Home's
 * (../../../components/corpus-search/use-search.ts): a short debounce, the
 * previous request aborted on every keystroke, the last good rows held
 * while the next load, and a per-tab cache by query so backspacing (and a
 * remount) is instant. Everything shown is derived from the responses by
 * query, so the effect only fetches. The server ranks with the shared
 * matcher and cuts at `limit`; the browser never holds more than a
 * screenful.
 */
export type PaletteStatus = 'loading' | 'ready' | 'error'

export interface PaletteState {
  entries: PaletteEntry[]
  /** Rows the query matched before the limit, and papers visible at all. */
  matched: number
  total: number
  status: PaletteStatus
  /** After a failure — or from a picker opened onto one. */
  retry: () => void
}

/** How long a tab keeps a settled palette before asking the server again. */
const PALETTE_TTL_MS = 45_000
const CACHE_MAX = 50
const LIMIT = 20
const DEBOUNCE_MS = 130

const EMPTY: Palette = { query: '', papers: [], matched: 0, total: 0 }

/** Per tab: settled palettes by query, newest last — what a remount starts from. */
const tab = new Map<string, { at: number; value: Palette }>()

function remember(q: string, value: Palette): void {
  tab.delete(q)
  tab.set(q, { at: Date.now(), value })
  while (tab.size > CACHE_MAX) {
    const oldest = tab.keys().next().value
    if (oldest === undefined) break
    tab.delete(oldest)
  }
}

/** The tab's still-fresh palettes, as a mount's starting point. */
function fresh(): Map<string, Palette> {
  const now = Date.now()
  const out = new Map<string, Palette>()
  for (const [q, { at, value }] of tab) if (now - at < PALETTE_TTL_MS) out.set(q, value)
  return out
}

export function palettePath(q: string, limit = LIMIT): string {
  return q ? `/bff/papers/palette?q=${encodeURIComponent(q)}&limit=${limit}` : '/bff/papers/palette'
}

/** Runs `fn` once the browser is idle (soon, whatever happens); returns the cancel. */
function onIdle(fn: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const id = window.requestIdleCallback(fn, { timeout: 1_000 })
    return () => window.cancelIdleCallback(id)
  }
  const id = window.setTimeout(fn, 0)
  return () => window.clearTimeout(id)
}

export function usePalette(query: string): PaletteState {
  const q = query.trim()
  const [entries, setEntries] = useState<ReadonlyMap<string, Palette>>(fresh)
  const [latest, setLatest] = useState<Palette | null>(() => entries.get('') ?? null)
  const [failed, setFailed] = useState<string | null>(null)
  // Bumped by retry; a retry asks the server again even for a cached query.
  const [attempt, setAttempt] = useState(0)
  const seq = useRef(0)
  const current = useRef('')
  const fetchedAttempt = useRef(0)
  const inFlight = useRef<{ q: string; controller: AbortController } | null>(null)

  const hit = entries.get(q)
  const error = hit === undefined && failed === q
  const status: PaletteStatus = error ? 'error' : hit !== undefined ? 'ready' : 'loading'
  const shown = hit ?? latest ?? EMPTY

  useEffect(() => {
    if (current.current !== q) {
      current.current = q
      seq.current += 1
    }
    const retrying = attempt !== fetchedAttempt.current
    if (!retrying && (entries.has(q) || inFlight.current?.q === q)) return
    const mine = seq.current
    const fire = () => {
      inFlight.current?.controller.abort()
      const controller = new AbortController()
      inFlight.current = { q, controller }
      fetchedAttempt.current = attempt
      bffFetch<Palette>(palettePath(q), { signal: controller.signal })
        .then((palette) => {
          remember(q, palette)
          setEntries((prev) => new Map(prev).set(q, palette))
          if (mine === seq.current) setLatest(palette)
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return
          console.error('[ask] palette failed:', e)
          if (mine === seq.current) setFailed(q)
        })
        .finally(() => {
          if (inFlight.current?.controller === controller) inFlight.current = null
        })
    }
    // The empty palette waits for an idle moment; a keystroke waits out the debounce.
    if (!q) return onIdle(fire)
    const timer = setTimeout(fire, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [q, attempt, entries])

  // Stable by the compiler's memoization; nothing here needs a manual one.
  const retry = () => {
    setFailed(null)
    setAttempt((n) => n + 1)
  }

  return { entries: shown.papers, matched: shown.matched, total: shown.total, status, retry }
}

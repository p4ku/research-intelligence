'use client'

import { bffFetch } from '@/lib/bff/client'
import type { Palette, PaletteEntry } from '@/lib/bff/papers/schema'
import { useCallback, useEffect, useRef, useState } from 'react'

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
 * while the next load, and a per-tab cache by query so backspacing is
 * instant. The server ranks with the shared matcher and cuts at `limit`,
 * so the browser never holds more than a screenful.
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

/** Per tab: settled palettes by query, newest last. */
const held = new Map<string, { at: number; value: Palette }>()

function remember(q: string, value: Palette): void {
  held.delete(q)
  held.set(q, { at: Date.now(), value })
  while (held.size > CACHE_MAX) {
    const oldest = held.keys().next().value
    if (oldest === undefined) break
    held.delete(oldest)
  }
}

function recall(q: string): Palette | undefined {
  const hit = held.get(q)
  if (!hit) return undefined
  if (Date.now() - hit.at >= PALETTE_TTL_MS) {
    held.delete(q)
    return undefined
  }
  return hit.value
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
  const [latest, setLatest] = useState<Palette>(() => recall('') ?? EMPTY)
  const [settled, setSettled] = useState<string | null>(() => (recall('') ? '' : null))
  const [failed, setFailed] = useState<string | null>(null)
  // Bumped by retry; a retry asks the server again even for a cached query.
  const [attempt, setAttempt] = useState(0)
  const seq = useRef(0)
  const inFlight = useRef<{ q: string; controller: AbortController } | null>(null)

  useEffect(() => {
    seq.current += 1
    const mine = seq.current
    const cached = attempt === 0 ? recall(q) : undefined
    if (cached) {
      setLatest(cached)
      setSettled(q)
      return
    }
    if (inFlight.current?.q === q && attempt === 0) return
    const fire = () => {
      inFlight.current?.controller.abort()
      const controller = new AbortController()
      inFlight.current = { q, controller }
      bffFetch<Palette>(palettePath(q), { signal: controller.signal })
        .then((palette) => {
          remember(q, palette)
          if (mine !== seq.current) return
          setLatest(palette)
          setSettled(q)
          setFailed(null)
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || mine !== seq.current) return
          console.error('[ask] palette failed:', error)
          setFailed(q)
        })
        .finally(() => {
          if (inFlight.current?.controller === controller) inFlight.current = null
        })
    }
    // The empty palette waits for an idle moment; a keystroke waits out the debounce.
    if (!q) return onIdle(fire)
    const timer = setTimeout(fire, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [q, attempt])

  const retry = useCallback(() => {
    setFailed(null)
    setAttempt((n) => n + 1)
  }, [])

  const status: PaletteStatus = failed === q ? 'error' : settled === q ? 'ready' : 'loading'
  return { entries: latest.papers, matched: latest.matched, total: latest.total, status, retry }
}

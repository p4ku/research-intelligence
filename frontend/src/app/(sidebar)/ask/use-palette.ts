'use client'

import { bffFetch } from '@/lib/bff/client'
import type { Palette, PaletteEntry } from '@/lib/bff/papers/schema'
import { useCallback, useEffect, useState } from 'react'

/**
 * The picker's corpus, fetched after the console has painted.
 *
 * Nothing on the empty canvas needs a paper until the reader reaches for
 * one, so the corpus is not worth a single blocked frame: the composer
 * renders at once, and the palette follows in the first idle moment — the
 * second or so it takes to find the picker is usually all the time it
 * needs. The server holds it in a short per-user cache, so asking again on
 * every visit costs almost nothing; one settled load is also kept per tab,
 * so a remount (a deep link's key, a route revisit) does not wait twice.
 */
export type PaletteStatus = 'loading' | 'ready' | 'error'

export interface PaletteState {
  entries: PaletteEntry[]
  status: PaletteStatus
  /** After a failure — or from a picker opened onto one. */
  retry: () => void
}

/** Mirrors the server cache's lifetime, so a tab never holds a corpus the server would not. */
const PALETTE_TTL_MS = 45_000

let held: { at: number; value: Promise<PaletteEntry[]> } | null = null

function loadPalette(force: boolean): Promise<PaletteEntry[]> {
  const now = Date.now()
  if (!force && held && now - held.at < PALETTE_TTL_MS) return held.value
  const value = bffFetch<Palette>('/bff/papers/palette').then((p) => p.papers)
  const entry = { at: now, value }
  held = entry
  value.catch(() => {
    if (held === entry) held = null
  })
  return value
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

export function usePalette(): PaletteState {
  const [state, setState] = useState<{ entries: PaletteEntry[]; status: PaletteStatus }>({
    entries: [],
    status: 'loading',
  })
  // Bumped by retry; the first attempt reuses whatever the tab already holds.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    const cancel = onIdle(() => {
      loadPalette(attempt > 0).then(
        (entries) => {
          if (live) setState({ entries, status: 'ready' })
        },
        (error: unknown) => {
          console.error('[ask] palette failed:', error)
          if (live) setState((s) => ({ entries: s.entries, status: 'error' }))
        },
      )
    })
    // Cancelling only matters before the load starts; afterwards `live` gates the result.
    return () => {
      live = false
      cancel()
    }
  }, [attempt])

  const retry = useCallback(() => {
    setState((s) => ({ entries: s.entries, status: 'loading' }))
    setAttempt((n) => n + 1)
  }, [])

  return { entries: state.entries, status: state.status, retry }
}

'use client'

import { BffClientError, bffFetch } from '@/lib/bff/client'
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
 *
 * A load that fails the way an outage fails (5xx, no response) gets one
 * quiet second attempt before the picker says so. The first request after
 * a deploy lands on instances seconds old, and a blip there heals itself
 * faster than the reader can reach for a paper; the retry announces itself
 * (a console line here, `?retry=1&after=` on the wire) so a healed blip is
 * still on record.
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

/** Long enough for a restarted instance to warm, short enough to beat the reader to the picker. */
export const PALETTE_RETRY_DELAY_MS = 1_500

/**
 * Whether a failed load is worth a second attempt: an outage (5xx, no
 * response) usually clears in a moment, whereas a 4xx says the same request
 * will fail the same way — and a 401 has already sent the reader to sign in.
 */
export function isTransient(error: unknown): boolean {
  return !(error instanceof BffClientError) || error.problem.status >= 500
}

/** The failure's problem slug (`upstream-error`), for the wire marker and the log line. */
export function failureSlug(error: unknown): string {
  if (!(error instanceof BffClientError)) return 'unknown'
  return error.problem.type.slice(error.problem.type.lastIndexOf('/') + 1) || 'unknown'
}

/** The retried request carries its reason, so the router's access log alone tells the story. */
export function paletteUrl(retryAfter?: string): string {
  if (!retryAfter) return '/bff/papers/palette'
  return `/bff/papers/palette?${new URLSearchParams({ retry: '1', after: retryAfter })}`
}

function fetchPalette(retryAfter?: string): Promise<PaletteEntry[]> {
  return bffFetch<Palette>(paletteUrl(retryAfter)).then((p) => p.papers)
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/**
 * One load with its single quiet retry: a transient failure is logged and
 * `load` is asked again after `delayMs`, told what went wrong the first
 * time; any other failure, and the second one, are the caller's to show.
 */
export async function withOneRetry<T>(
  load: (retryAfter?: string) => Promise<T>,
  delayMs = PALETTE_RETRY_DELAY_MS,
): Promise<T> {
  try {
    return await load()
  } catch (error) {
    if (!isTransient(error)) throw error
    const after = failureSlug(error)
    console.warn(`[ask] palette failed (${after}); retrying once in ${delayMs} ms`)
    await wait(delayMs)
    return load(after)
  }
}

let held: { at: number; value: Promise<PaletteEntry[]> } | null = null

function loadPalette(force: boolean): Promise<PaletteEntry[]> {
  const now = Date.now()
  if (!force && held && now - held.at < PALETTE_TTL_MS) return held.value
  const value = withOneRetry(fetchPalette)
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

'use client'

import { BffClientError, bffFetch } from '@/lib/bff/client'
import { problemSlug } from '@/lib/bff/core/problem'
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

/** How long a tab keeps a settled palette before asking the server again. */
const PALETTE_TTL_MS = 45_000

/** Short enough to beat the reader to the picker; a blip that lasts longer is shown. */
const PALETTE_RETRY_DELAY_MS = 1_500

/** A load slower than this is a failure, not a wait: bones for longer are worse than the error row. */
const PALETTE_TIMEOUT_MS = 15_000

/**
 * Whether a failed load is worth a second attempt: an outage (5xx, no
 * response, a timeout) usually clears in a moment, whereas a 4xx says the
 * same request will fail the same way — and a 401 has already sent the
 * reader to sign in.
 */
export function isTransient(error: unknown): boolean {
  return !(error instanceof BffClientError) || error.problem.status >= 500
}

/** The failure's problem slug (`upstream-error`), for the wire marker and the log line. */
export function failureSlug(error: unknown): string {
  if (error instanceof BffClientError) return problemSlug(error.problem.type) || 'unknown'
  if (error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')) {
    return 'timeout'
  }
  return 'unknown'
}

/**
 * The retried request carries its reason, so the router's access log alone
 * tells the story. The reason is a slug and nothing else — it ends up in a
 * log line — so anything that is not one is dropped before it goes out.
 */
export function paletteUrl(retryAfter?: string): string {
  const after = retryAfter?.replace(/[^a-z0-9-]/g, '').slice(0, 64)
  if (!after) return '/bff/papers/palette'
  return `/bff/papers/palette?${new URLSearchParams({ retry: '1', after })}`
}

function fetchPalette(retryAfter?: string): Promise<PaletteEntry[]> {
  return bffFetch<Palette>(paletteUrl(retryAfter), {
    signal: AbortSignal.timeout(PALETTE_TIMEOUT_MS),
  }).then((p) => p.papers)
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

/**
 * `force` is a person pressing Try again (or opening the picker onto an
 * error): one honest attempt, no quiet retry behind it — the automatic
 * second chance belongs to the load nobody asked for.
 */
function loadPalette(force: boolean): Promise<PaletteEntry[]> {
  const now = Date.now()
  if (!force && held && now - held.at < PALETTE_TTL_MS) return held.value
  const value = force ? fetchPalette() : withOneRetry(fetchPalette)
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
          if (!live) return
          console.error('[ask] palette failed:', error)
          setState((s) => ({ entries: s.entries, status: 'error' }))
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

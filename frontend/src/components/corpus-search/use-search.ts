'use client'

import { bffFetch } from '@/lib/bff/client'
import type { SearchResponse } from '@/lib/bff/search/schema'
import { useEffect, useRef, useState } from 'react'

export interface SearchState {
  /** The response for the current text, or the last good one while it loads. */
  result: SearchResponse | null
  /** No response for the current text yet (debounce or fetch in flight). */
  pending: boolean
  /** The request for the current text failed for a reason other than being superseded. */
  error: boolean
}

/** Two characters is where a query stops being a keystroke. */
const MIN_LENGTH = 2
const CACHE_MAX = 50

export function searchPath(q: string, limit: number): string {
  return `/bff/search?q=${encodeURIComponent(q)}&limit=${limit}`
}

function remember(
  entries: ReadonlyMap<string, SearchResponse>,
  q: string,
  result: SearchResponse,
): ReadonlyMap<string, SearchResponse> {
  const next = new Map(entries)
  next.delete(q)
  next.set(q, result)
  while (next.size > CACHE_MAX) {
    const oldest = next.keys().next().value
    if (oldest === undefined) break
    next.delete(oldest)
  }
  return next
}

/**
 * Typeahead fetching with the manners a fast field needs: a short debounce,
 * the previous request aborted on every keystroke, out-of-order responses
 * kept only under their own query, the last good result held while the
 * next loads, and a per-mount cache so backspacing is instant.
 *
 * Everything shown is derived from three pieces of state — responses by
 * query, the newest response, the query that failed — so the effect only
 * fetches; it never sets state on its own.
 */
export function useSearch(
  query: string,
  { limit, debounceMs = 130 }: { limit: number; debounceMs?: number },
): SearchState {
  const q = query.trim()
  const eligible = q.length >= MIN_LENGTH
  const [entries, setEntries] = useState<ReadonlyMap<string, SearchResponse>>(() => new Map())
  const [latest, setLatest] = useState<SearchResponse | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const seq = useRef(0)
  const current = useRef('')
  const inFlight = useRef<{ q: string; controller: AbortController } | null>(null)

  const hit = eligible ? entries.get(q) : undefined
  const error = eligible && hit === undefined && failed === q
  const pending = eligible && hit === undefined && !error
  const result = eligible ? (hit ?? latest) : null

  useEffect(() => {
    if (current.current !== q) {
      current.current = q
      seq.current += 1
    }
    if (!eligible) {
      inFlight.current?.controller.abort()
      inFlight.current = null
      return
    }
    if (entries.has(q) || inFlight.current?.q === q) return
    const mine = seq.current
    const timer = setTimeout(() => {
      inFlight.current?.controller.abort()
      const controller = new AbortController()
      inFlight.current = { q, controller }
      // A retry for this text starts clean, so an old failure for the same
      // query cannot flash as an outage while the new request is in flight.
      setFailed((f) => (f === q ? null : f))
      bffFetch<SearchResponse>(searchPath(q, limit), { signal: controller.signal })
        .then((response) => {
          setEntries((prev) => remember(prev, q, response))
          if (mine === seq.current) setLatest(response)
        })
        .catch(() => {
          if (controller.signal.aborted) return
          // No sequence gate here: `error` is read against the current q, so a
          // key for a query the user has left is inert, while gating would
          // strand a query they backspaced back to as pending forever.
          setFailed(q)
        })
        .finally(() => {
          if (inFlight.current?.controller === controller) inFlight.current = null
        })
    }, debounceMs)
    return () => clearTimeout(timer)
  }, [q, eligible, limit, debounceMs, entries])

  return { result, pending, error }
}

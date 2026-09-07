/**
 * Walk a paginated list newest-first until it ends or a bound says stop.
 *
 * Django's list endpoints order `-created_at, -id`, so "the newest N" is
 * literally "stop after N": a cap never reads a page it will not keep. The
 * fetch is injected (one page at a time), which keeps this pure and lets
 * the snapshot's policy be tested without a backend. Sequential on purpose —
 * each page decides whether the next is needed.
 */
import type { Page } from './pagination'
import { problem } from './problem'

export interface DrainOptions<T> {
  /** Items per page; Django's `max_page_size` is 500. */
  pageSize: number
  /** Keep at most this many items — the newest, given the upstream order. */
  maxItems: number
  /** Dedupe key: a run writing rows between two page reads can shift a row across pages. */
  id: (item: T) => string
  /** Stop before this item (it and everything after it are dropped). */
  until?: (item: T) => boolean
}

export interface Drained<T> {
  items: T[]
  /** The upstream `count` — every row the list holds, kept or not. */
  total: number
  /** JSON bytes as received, summed over the pages read. */
  bytes: number
  pages: number
}

export interface FetchedPage<T> {
  page: Page<T>
  bytes: number
}

export async function drain<T>(
  fetchPage: (page: number, pageSize: number) => Promise<FetchedPage<T>>,
  { pageSize, maxItems, id, until }: DrainOptions<T>,
): Promise<Drained<T>> {
  const items: T[] = []
  const seen = new Set<string>()
  let total = 0
  let bytes = 0
  let pages = 0
  for (let n = 1; ; n += 1) {
    const { page, bytes: size } = await fetchPage(n, pageSize)
    pages += 1
    bytes += size
    if (n === 1) total = page.count
    if (page.results.length === 0 && page.next !== null) {
      throw problem('upstream-shape', {
        detail: `An empty page ${n} still pointed at a next page.`,
      })
    }
    for (const item of page.results) {
      if (until?.(item)) return { items, total, bytes, pages }
      const key = id(item)
      if (seen.has(key)) continue
      seen.add(key)
      items.push(item)
      if (items.length >= maxItems) return { items, total, bytes, pages }
    }
    if (page.next === null) return { items, total, bytes, pages }
  }
}

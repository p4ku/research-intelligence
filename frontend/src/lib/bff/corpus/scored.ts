/**
 * The user's scored papers: every domain's list, merged newest-first, under
 * one cap.
 *
 * Django's scorecard is served per workspace and newest-first, so the
 * per-user corpus is a merge: the first page of every membership gives each
 * domain's size and the head of its list, then rows are taken from whichever
 * domain holds the newest one, a domain's next page read only when its
 * buffer runs dry. The cap therefore keeps the newest `cap` papers across
 * all domains, as the raw corpus's single newest-first list did, and never a
 * whole domain at the expense of another — so "the newest `kept` of `total`"
 * is literally true. The fetch is injected (one page of one domain at a
 * time), which keeps this pure and lets the policy be tested without a
 * backend. Sequential on purpose: each page decides whether another is
 * needed, and one drain in flight is enough load on Django.
 */
import type { FetchedPage } from '../core/drain'
import { problem } from '../core/problem'
import { truncation } from './window'

export interface ScoredDrainOptions {
  /** Items per page; Django clamps the scorecard's `page_size` to 200. */
  pageSize: number
  /** Papers kept per user across every domain. */
  cap: number
}

export interface ScoredDrained<T> {
  /** Every domain walked, in the order given, each newest-first; empty when nothing of it made the cap. */
  byWorkspace: Map<string, T[]>
  /** Set when the cap dropped papers: the newest `kept` of `total` are here. */
  truncated?: { kept: number; total: number }
  /** Bytes as `fetchPage` reported them, summed over every page of every domain. */
  bytes: number
}

interface Cursor<T> {
  workspaceId: string
  /** Rows read and not yet taken, newest first. */
  buffer: T[]
  /** Pages read so far. */
  page: number
  /** Whether Django said there is a page after the last one read. */
  more: boolean
  /** Ids already taken or buffered: a run writing rows between two page reads can shift a row across pages. */
  seen: Set<string>
}

/** The instant a row was created; unparseable dates sort oldest. */
function createdAt(row: { created_at: string }): number {
  const at = Date.parse(row.created_at)
  return Number.isNaN(at) ? Number.NEGATIVE_INFINITY : at
}

export async function drainScored<T extends { id: string; created_at: string }>(
  workspaceIds: readonly string[],
  fetchPage: (workspaceId: string, page: number, pageSize: number) => Promise<FetchedPage<T>>,
  { pageSize, cap }: ScoredDrainOptions,
): Promise<ScoredDrained<T>> {
  // No domain contributes more than `cap` rows, so no page needs more; the
  // size must then stay the same for every page of a domain, or page numbers
  // would not line up.
  const size = Math.min(pageSize, cap)
  const byWorkspace = new Map<string, T[]>()
  const cursors: Cursor<T>[] = []
  let total = 0
  let bytes = 0

  async function read(cursor: Cursor<T>): Promise<void> {
    cursor.page += 1
    const { page, bytes: read } = await fetchPage(cursor.workspaceId, cursor.page, size)
    bytes += read
    if (cursor.page === 1) total += page.count
    if (page.results.length === 0 && page.next !== null) {
      throw problem('upstream-shape', {
        detail: `An empty page ${cursor.page} of workspace ${cursor.workspaceId} still pointed at a next page.`,
      })
    }
    cursor.more = page.next !== null
    for (const row of page.results) {
      if (cursor.seen.has(row.id)) continue
      cursor.seen.add(row.id)
      cursor.buffer.push(row)
    }
  }

  for (const workspaceId of workspaceIds) {
    byWorkspace.set(workspaceId, [])
    const cursor: Cursor<T> = { workspaceId, buffer: [], page: 0, more: false, seen: new Set() }
    cursors.push(cursor)
    await read(cursor)
  }

  let kept = 0
  while (kept < cap) {
    let newest: Cursor<T> | null = null
    for (const cursor of cursors) {
      // A dry buffer with more pages must be refilled before it can be
      // compared: its next row may be newer than every other head.
      while (cursor.buffer.length === 0 && cursor.more) await read(cursor)
      const head = cursor.buffer[0]
      if (head === undefined) continue
      if (newest === null || createdAt(head) > createdAt(newest.buffer[0]!)) newest = cursor
    }
    if (newest === null) break
    byWorkspace.get(newest.workspaceId)!.push(newest.buffer.shift()!)
    kept += 1
  }
  return { byWorkspace, truncated: truncation(kept, total, cap), bytes }
}

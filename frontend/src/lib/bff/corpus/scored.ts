/**
 * The user's scored papers: one drain per domain, under one cap.
 *
 * Django's scorecard is served per workspace and newest-first, so the
 * per-user corpus is the memberships walked in turn, each domain's pages
 * read until its list ends or the cap is reached. The cap is shared: an
 * analyst with more history than `cap` across all their domains keeps the
 * newest papers of the domains walked first and sees the `truncated` line,
 * never a slower page or an outage. Past the cap a domain is asked for one
 * row, so its size still counts. The fetch is injected (one page of one
 * domain at a time), which keeps this pure and lets the policy be tested
 * without a backend.
 */
import { drain, type FetchedPage } from '../core/drain'
import { truncation } from './window'

export interface ScoredDrainOptions {
  /** Items per page; Django clamps the scorecard's `page_size` to 200. */
  pageSize: number
  /** Papers kept per user across every domain. */
  cap: number
}

export interface ScoredDrained<T> {
  /** Every domain walked, in the order given; empty past the cap. */
  byWorkspace: Map<string, T[]>
  /** Set when the cap dropped papers: the newest `kept` of `total` are here. */
  truncated?: { kept: number; total: number }
  /** JSON bytes as received, every page of every domain. */
  bytes: number
}

export async function drainScored<T extends { id: string }>(
  workspaceIds: readonly string[],
  fetchPage: (workspaceId: string, page: number, pageSize: number) => Promise<FetchedPage<T>>,
  { pageSize, cap }: ScoredDrainOptions,
): Promise<ScoredDrained<T>> {
  const byWorkspace = new Map<string, T[]>()
  let kept = 0
  let total = 0
  let bytes = 0
  for (const workspaceId of workspaceIds) {
    const remaining = cap - kept
    if (remaining <= 0) {
      const { page, bytes: size } = await fetchPage(workspaceId, 1, 1)
      byWorkspace.set(workspaceId, [])
      total += page.count
      bytes += size
      continue
    }
    const drained = await drain((page, size) => fetchPage(workspaceId, page, size), {
      pageSize: Math.min(pageSize, remaining),
      maxItems: remaining,
      id: (paper) => paper.id,
    })
    byWorkspace.set(workspaceId, drained.items)
    kept += drained.items.length
    total += drained.total
    bytes += drained.bytes
  }
  return { byWorkspace, truncated: truncation(kept, total, cap), bytes }
}

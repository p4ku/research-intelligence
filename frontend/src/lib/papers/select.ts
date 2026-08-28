// Small selectors over the domain types, safe for client components.

import type { Dimension, ScoredPaper, WorkspaceSummary } from './types'

export function trlDimension(paper: ScoredPaper): Dimension | undefined {
  return paper.dimensions.find((d) => d.is_trl)
}

export function dimensionByKey(paper: ScoredPaper, key: string): Dimension | undefined {
  return paper.dimensions.find((d) => d.key === key)
}

/** Definitions worth sorting/filtering by: active and, in this corpus, numeric. */
export function numericDefinitions(ws: WorkspaceSummary, papers: ScoredPaper[]) {
  return ws.definitions.filter(
    (d) => d.is_active && papers.some((p) => dimensionByKey(p, d.key)?.value !== null),
  )
}

/** Sort comparator: descending by value, nulls last. */
export function byValueDesc(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  return b - a
}

/** "95.5" → 96, "12.25" → 12.3; integers stay integers. */
export function formatScore(n: number | null): string {
  if (n === null) return '—'
  if (Number.isInteger(n)) return String(n)
  return (Math.round(n * 10) / 10).toString()
}

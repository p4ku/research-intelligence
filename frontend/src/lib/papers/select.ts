// Small selectors over the domain types, safe for client components.

import type { DefinitionSummary, Dimension, ScoredPaper, WorkspaceSummary } from './types'

/** A title up to its first colon — the part people say out loud. */
export const shortTitle = (title: string) => title.split(':')[0]!

/**
 * A title trimmed to at most `max` characters (default 50) for headers and
 * breadcrumbs. Cuts at the last word boundary inside the budget when one
 * falls in the second half, so a crumb ends on a word rather than mid-word,
 * and closes with the ellipsis glyph the rest of the copy uses (U+2026), not
 * three periods.
 */
export function trimTitle(title: string, max = 50): string {
  if (!title) return ''
  const trimmed = title.trim()
  if (trimmed.length <= max) return trimmed
  const head = trimmed.slice(0, max)
  const boundary = head.lastIndexOf(' ')
  const cut = boundary >= max / 2 ? head.slice(0, boundary) : head
  return `${cut.trimEnd()}…`
}

export function trlDimension(paper: ScoredPaper): Dimension | undefined {
  return (paper.dimensions ?? []).find((d) => d.is_trl)
}

export function dimensionByKey(paper: ScoredPaper, key: string): Dimension | undefined {
  return (paper.dimensions ?? []).find((d) => d.key === key)
}

/** Definitions worth sorting/filtering by: active and, in this corpus, numeric. */
export function numericDefinitions(
  ws: Pick<WorkspaceSummary, 'definitions'>,
  papers: ScoredPaper[],
) {
  return ws.definitions.filter(
    (d) => d.is_active && papers.some((p) => dimensionByKey(p, d.key)?.value !== null),
  )
}

/**
 * One definition list spanning several domains, each key once (the first
 * domain's entry wins) — so a sort option is offered once even when every
 * domain defines the same dimension.
 */
export function unionDefinitions(
  workspaces: readonly Pick<WorkspaceSummary, 'definitions'>[],
): DefinitionSummary[] {
  const seen = new Set<string>()
  const out: DefinitionSummary[] = []
  for (const ws of workspaces) {
    for (const d of ws.definitions) {
      if (seen.has(d.key)) continue
      seen.add(d.key)
      out.push(d)
    }
  }
  return out
}

/** Sort comparator: descending by value, nulls last. */
export function byValueDesc(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  return b - a
}

/** Sort comparator: ascending by value, nulls still last. */
export function byValueAsc(a: number | null, b: number | null): number {
  if (a === null || b === null) return byValueDesc(a, b)
  return a - b
}

/** "95.5" → 96, "12.25" → 12.3; integers stay integers. */
export function formatScore(n: number | null): string {
  if (n === null) return '—'
  if (Number.isInteger(n)) return String(n)
  return (Math.round(n * 10) / 10).toString()
}

// Small selectors over the domain types, safe for client components.

import { formatNumber, type Lang } from '@/lib/i18n'
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

/**
 * Whether a dimension is the workspace's Schwarz Fit, under either of the
 * two names it arrives with (the same pair dimension-label.ts maps). The card
 * leads its strip with it.
 */
export function isFitDimension(d: Pick<Dimension, 'name'>): boolean {
  const name = d.name.trim().toLowerCase()
  return name === 'schwarz fit' || name === 'fit score'
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

/**
 * A score as a reader sees it: the whole number, or the dash when there is
 * none. Rounds half up (74.5 → "75"); no locale, since a whole number under
 * a thousand reads the same in German and English. Thresholds and sorts
 * never read this — they compare the exact stored value (see `score.ts`).
 */
export function formatScore(n: number | null | undefined): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  return String(Math.round(n))
}

/**
 * A dimension or sub-measure figure. Score-like scales (no `max`, or a `max`
 * of nine or more — the 0–100 definitions and TRL) read as whole numbers;
 * a small scale such as a 0–1 confidence or a 0–5 ratio keeps up to two
 * decimals, so 0.92 does not print as "1".
 */
export function formatMeasure(
  value: number | null | undefined,
  max: number | null | undefined,
  lang: Lang,
): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (max === null || max === undefined || max >= 9) return formatScore(value)
  return formatNumber(value, lang, undefined, 2)
}

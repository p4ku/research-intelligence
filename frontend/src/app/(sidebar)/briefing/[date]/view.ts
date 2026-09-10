/**
 * How a briefing's papers are viewed: the sort and the score floor, as the
 * URL carries them and as the list applies them. Pure, so the list derives
 * every render from `useSearchParams` (see docs/skeletons.md's URL-state
 * rule) and bun tests the arithmetic. Defaults stay out of the URL, so a
 * briefing's permalink (`?domain=&run=`) is untouched until a reader
 * changes the view.
 *
 * Everything here works on the papers in hand — a briefing is one run's
 * list, never paged — so no BFF round trip is involved.
 */
import type { T } from '@/lib/i18n'
import { dimensionShortName } from '@/lib/papers/dimension-label'
import { byValueDesc, dimensionByKey } from '@/lib/papers/select'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'

/** 'score' (the Schwarz Score) | 'published' | 'dim:<definition key>' */
export type EditionSort = string

export interface EditionView {
  sort: EditionSort
  /** The Schwarz Score floor; 0 = every paper. */
  minScore: number
}

export const DEFAULT_VIEW: EditionView = { sort: 'score', minScore: 0 }

/** The slider's range: the score is read on a 0–100 scale, in steps of five. */
export const SCORE_CEILING = 100
export const SCORE_STEP = 5

// A dimension key is the backend's: snake_case, though a name's parentheses survive
// ("technology_readiness_level_(trl)" on prod). Bounded, never trusted further
// than a lookup.
const SORT_RE = /^(score|published|dim:[\w().-]{1,120})$/

/** The view a URL's params describe; anything unusable takes its default. */
export function viewFrom(params: Record<string, string | string[] | undefined>): EditionView {
  const one = (key: string): string | undefined => {
    const v = params[key]
    return Array.isArray(v) ? v[0] : v
  }
  const sort = one('sort') ?? ''
  const score = one('score') ?? ''
  const min = /^\d+$/.test(score) ? Number(score) : 0
  return {
    sort: SORT_RE.test(sort) ? sort : DEFAULT_VIEW.sort,
    minScore: min > 0 && min <= SCORE_CEILING ? min : 0,
  }
}

/**
 * The URL's query with this view written into it — the briefing's own
 * params (`domain`, `run`) kept as they are, the view's dropped when they
 * are the default. Returns '' for a bare permalink.
 */
export function searchWith(current: string, view: EditionView): string {
  const q = new URLSearchParams(current)
  if (view.sort === DEFAULT_VIEW.sort) q.delete('sort')
  else q.set('sort', view.sort)
  if (view.minScore > 0) q.set('score', String(view.minScore))
  else q.delete('score')
  const s = q.toString()
  return s ? `?${s}` : ''
}

export function isDefaultView(view: EditionView): boolean {
  return view.sort === DEFAULT_VIEW.sort && view.minScore === 0
}

export interface SortOption {
  id: EditionSort
  label: string
}

/** A dimension the list can order by: scored, and not the affiliation flags. */
function sortable(d: Dimension): boolean {
  if (d.is_risk_and_affiliation || d.key.includes('risk_and_affiliation')) return false
  return typeof d.value === 'number' && Number.isFinite(d.value)
}

/**
 * The sorts on offer for these papers: the Schwarz Score, the publication
 * date, then one per scored dimension — TRL included — in the workspace's
 * definition order, each key once. A dimension no paper in the briefing
 * scored is not offered: an order by it would change nothing.
 */
export function sortOptions(papers: readonly ScoredPaper[], t: T): SortOption[] {
  const seen = new Map<string, { d: Dimension; order: number; index: number }>()
  let index = 0
  for (const p of papers) {
    for (const d of p.dimensions ?? []) {
      if (!sortable(d) || seen.has(d.key)) continue
      seen.set(d.key, { d, order: d.order ?? Number.MAX_SAFE_INTEGER, index: index++ })
    }
  }
  const dims = [...seen.values()]
    .sort((a, b) => a.order - b.order || a.index - b.index)
    .map(({ d }) => ({ id: `dim:${d.key}`, label: dimensionShortName(d, t) }))
  return [
    { id: 'score', label: t('Schwarz Score') },
    { id: 'published', label: t('Date published') },
    ...dims,
  ]
}

/** The papers as the view orders and narrows them; the input is not touched. */
export function applyView(papers: readonly ScoredPaper[], view: EditionView): ScoredPaper[] {
  const kept =
    view.minScore > 0
      ? papers.filter((p) => p.signal_score !== null && p.signal_score >= view.minScore)
      : [...papers]
  // Array.prototype.sort is stable: equal keys keep the briefing's own order.
  if (view.sort === 'published') {
    return kept.sort((a, b) => byDateDesc(a.published_date, b.published_date))
  }
  if (view.sort.startsWith('dim:')) {
    const key = view.sort.slice(4)
    const value = (p: ScoredPaper) => {
      const d = dimensionByKey(p, key)
      return d && sortable(d) ? d.value : null
    }
    return kept.sort((a, b) => byValueDesc(value(a), value(b)))
  }
  return kept.sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
}

/** Newest first; a paper without a date last. ISO dates compare as strings. */
function byDateDesc(a: string | null, b: string | null): number {
  if (a === b) return 0
  if (a === null) return 1
  if (b === null) return -1
  return a < b ? 1 : -1
}

/**
 * How a briefing's papers are viewed: the sort, the score floor and the
 * page, as the URL carries them and as the list applies them. Pure, so the
 * list derives every render from `useSearchParams` (a Back is served from
 * the router cache, so the view is never seeded from a prop) and bun tests
 * the arithmetic. Defaults stay out of the URL, so a briefing's permalink
 * (`?domain=&run=`) is untouched until a reader changes the view.
 *
 * Everything here works on the papers in hand — a briefing is one run's
 * list, sorted and narrowed whole and only then cut into pages — so no BFF
 * round trip is involved.
 */
import type { T } from '@/lib/i18n'
import { dimensionShortName } from '@/lib/papers/dimension-label'
import { SCORE_CEILING, SCORE_STEP } from '@/lib/papers/score'
import { byValueDesc, dimensionByKey } from '@/lib/papers/select'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'

/** 'score' (the Schwarz Score) | 'published' | 'dim:<definition key>' */
export type EditionSort = string

export interface EditionView {
  sort: EditionSort
  /** The Schwarz Score floor; 0 = every paper. */
  minScore: number
  /** 1-based; the first page stays out of the URL. */
  page: number
  /** Dynamic numeric dimension filters: key -> minimum value */
  dimensionFilters?: Record<string, number>
}

export const DEFAULT_VIEW: EditionView = {
  sort: 'score',
  minScore: 0,
  page: 1,
}

/**
 * Cards per page. A briefing on prod ran to 566 papers (Hybrid Computing,
 * 7 Sep 2026); twenty is a screen's worth of reading before the pager, and
 * keeps the DOM to a size a phone scrolls without stutter.
 */
export const PAGE_SIZE = 20

// A page number is a bounded positive integer; anything else is the first
// page. Six digits is far past any list the page could hold.
const PAGE_RE = /^[1-9]\d{0,5}$/

/**
 * The slider's range: the score is read on a 0–100 scale, one point a step.
 * One rule for the ceiling and the step, so the rail cannot drift from the
 * cap the parse seam applies — re-exported under the names the list already
 * imports from here.
 */
export { SCORE_CEILING, SCORE_STEP } from '@/lib/papers/score'

// A dimension key is the backend's own: lower-cased, spaces and hyphens turned
// to underscores, everything else kept ("sovereign_cloud_&_commercial_viability",
// "technology_readiness_level_(trl)", non-ASCII letters). Any key the rail can
// offer must read back, so only whitespace is refused. Bounded, and only ever
// used as a lookup.
const SORT_RE = /^(score|published|dim:\S{1,120})$/

/** The view a URL's params describe; anything unusable takes its default. */
export function viewFrom(params: Record<string, string | string[] | undefined>): EditionView {
  const one = (key: string): string | undefined => {
    const v = params[key]
    return Array.isArray(v) ? v[0] : v
  }
  const sort = one('sort') ?? ''
  const score = one('score') ?? ''
  const page = one('page') ?? ''
  const min = /^\d+$/.test(score) ? Number(score) : 0

  const dimensionFilters: Record<string, number> = {}
  for (const [k, v] of Object.entries(params)) {
    if (!v) continue
    const valStr = Array.isArray(v) ? v[0] : v
    if (!valStr || !/^\d+(\.\d+)?$/.test(valStr)) continue
    const num = Number(valStr)
    if (num <= 0) continue

    let dimKey: string | null = null
    if (k.startsWith('dim_min:')) dimKey = k.slice(8)
    else if (k.startsWith('min_dim:')) dimKey = k.slice(8)
    else if (k.startsWith('dim:')) dimKey = k.slice(4)
    else if (k.startsWith('min_') && k !== 'min_score' && k !== 'min_date' && k !== 'min_created_at') {
      dimKey = k.slice(4)
    }

    if (dimKey) {
      dimensionFilters[dimKey.trim().toLowerCase()] = num
    }
  }

  return {
    sort: SORT_RE.test(sort) ? sort : DEFAULT_VIEW.sort,
    // Only a floor the thumb can land on: within the ceiling and on the step,
    // so the figure over the track never disagrees with the track. The step
    // test is idle while the step is one point — it is what re-arms the rule
    // if the step ever grows again.
    minScore: min > 0 && min <= SCORE_CEILING && min % SCORE_STEP === 0 ? min : 0,
    page: PAGE_RE.test(page) ? Number(page) : 1,
    ...(Object.keys(dimensionFilters).length > 0 ? { dimensionFilters } : {}),
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
  if (view.page > 1) q.set('page', String(view.page))
  else q.delete('page')

  // Remove existing min_* or dim:* params from query before writing active ones
  for (const key of Array.from(q.keys())) {
    if (
      (key.startsWith('min_') && key !== 'min_score' && key !== 'min_date' && key !== 'min_created_at') ||
      key.startsWith('dim:') ||
      key.startsWith('dim_min:') ||
      key.startsWith('min_dim:')
    ) {
      q.delete(key)
    }
  }
  if (view.dimensionFilters) {
    for (const [dimKey, minVal] of Object.entries(view.dimensionFilters)) {
      if (minVal > 0) {
        q.set(`min_${dimKey}`, String(minVal))
      }
    }
  }

  const s = q.toString()
  return s ? `?${s}` : ''
}

/**
 * Whether the sort and the floor are the defaults. The page is not a
 * filter: being on page three is nothing "Reset filters" should offer to
 * undo, and a reset lands on the first page anyway.
 */
export function isDefaultView(view: EditionView): boolean {
  const noDimFilters =
    !view.dimensionFilters || Object.values(view.dimensionFilters).every((v) => !v || v <= 0)
  return view.sort === DEFAULT_VIEW.sort && view.minScore === 0 && noDimFilters
}

export interface Page<T> {
  rows: T[]
  /** The page shown: the one asked for, folded back onto the last when past the end. */
  page: number
  pageCount: number
  /** 1-based positions of the first and last row shown; 0–0 for an empty list. */
  from: number
  to: number
}

/**
 * One page of an already ordered and narrowed list. A page past the end (a
 * link shared from page nine, then the floor raised) shows the last page
 * rather than an empty one; an empty list is one empty page, so the pager
 * has nothing to draw.
 */
export function pageOf<T>(rows: readonly T[], asked: number, size = PAGE_SIZE): Page<T> {
  const pageCount = Math.max(1, Math.ceil(rows.length / size))
  const page = Math.min(Math.max(1, asked), pageCount)
  const start = (page - 1) * size
  const slice = rows.slice(start, start + size)
  return {
    rows: slice,
    page,
    pageCount,
    from: slice.length ? start + 1 : 0,
    to: start + slice.length,
  }
}

/**
 * The view with a sort the list can honour. A `dim:` key none of these
 * papers carries (a hand-edited link, a definition renamed since the link
 * was shared, a scorecard read that came back empty) falls back to the
 * score, so the rail always marks the order the list is in.
 */
export function withKnownSort(view: EditionView, options: readonly SortOption[]): EditionView {
  return options.some((o) => o.id === view.sort) ? view : { ...view, sort: DEFAULT_VIEW.sort }
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

export interface DefinitionMeta {
  id?: string
  key: string
  name: string
  order?: number
  is_trl?: boolean
  max?: number
  is_numeric?: boolean
}

/**
 * The sorts on offer for these papers: the Schwarz Score, the publication
 * date when any paper has one, then one per scored dimension — TRL included — in the workspace's
 * definition order, each key once. When definitions are provided, they supply
 * the dimension options even if the current page of papers is filtered down.
 */
export function sortOptions(
  papers: readonly ScoredPaper[],
  t: T,
  definitions?: readonly DefinitionMeta[],
): SortOption[] {
  let dims: SortOption[] = []
  if (definitions && definitions.length > 0) {
    dims = [...definitions]
      .filter((d) => !d.key.includes('risk_and_affiliation') && d.is_numeric !== false)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .map((d) => ({
        id: `dim:${d.key}`,
        label: dimensionShortName(
          {
            name: d.name,
            is_trl: Boolean(
              d.is_trl ?? (d.name.toLowerCase().includes('trl') || d.key.includes('trl')),
            ),
          },
          t,
        ),
      }))
  } else {
    const seen = new Map<string, { d: Dimension; order: number; index: number }>()
    let index = 0
    for (const p of papers) {
      for (const d of p.dimensions ?? []) {
        if (!sortable(d) || seen.has(d.key)) continue
        seen.set(d.key, { d, order: d.order ?? Number.MAX_SAFE_INTEGER, index: index++ })
      }
    }
    dims = [...seen.values()]
      .sort((a, b) => a.order - b.order || a.index - b.index)
      .map(({ d }) => ({ id: `dim:${d.key}`, label: dimensionShortName(d, t) }))
  }
  // The same rule for the date: the editions endpoint sends no publication
  // date, and the scorecard may not either, so an order by it would leave the
  // list as it was. The option appears once any paper carries one.
  const dated = papers.some((p) => Boolean(p.published_date))
  return [
    { id: 'score', label: t('Total Score') },
    ...(dated ? [{ id: 'published', label: t('Date published') }] : []),
    ...dims,
  ]
}

/** The papers as the view orders and narrows them; the input is not touched. */
export function applyView(papers: readonly ScoredPaper[], view: EditionView): ScoredPaper[] {
  let kept =
    view.minScore > 0
      ? papers.filter((p) => p.signal_score !== null && p.signal_score >= view.minScore)
      : [...papers]

  if (view.dimensionFilters) {
    for (const [dimKey, minVal] of Object.entries(view.dimensionFilters)) {
      if (minVal > 0) {
        kept = kept.filter((p) => {
          const d = dimensionByKey(p, dimKey)
          return d && typeof d.value === 'number' && Number.isFinite(d.value) && d.value >= minVal
        })
      }
    }
  }

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

/**
 * Newest first; a paper without a date last. ISO dates compare as strings.
 * A missing field counts as no date: edition rows are cast from a schema
 * where `published_date` is optional, and `undefined` must not escape the
 * null checks and make the order depend on the input's.
 */
function byDateDesc(a: string | null | undefined, b: string | null | undefined): number {
  const x = a ?? null
  const y = b ?? null
  if (x === y) return 0
  if (x === null) return 1
  if (y === null) return -1
  return x < y ? 1 : -1
}

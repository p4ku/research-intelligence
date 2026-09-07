/**
 * The Papers page's state — filters, sort, search and page — as the URL
 * carries it, and as the BFF is asked for it. Pure, so the page composes
 * the first page on the server from `searchParams`, the browser derives
 * every render from `useSearchParams`, and bun tests both. Defaults are
 * omitted from the URL so a plain `/papers` stays clean; `?q=` is Home's
 * search handing over.
 */
import type { PapersQuery } from '@/lib/bff/papers/schema'

/** The spec's page size — the browser and its skeleton share it. */
export const PER_PAGE = 8

export type Screening = PapersQuery['screening'] extends infer S
  ? S extends 'passed' | 'borderline' | 'pending' | 'rejected' | 'withdrawn' | 'all'
    ? S
    : never
  : never

const SCREENINGS: readonly Screening[] = [
  'passed',
  'borderline',
  'pending',
  'rejected',
  'withdrawn',
  'all',
]

export interface BrowseState {
  q: string
  /** A workspace id, or null for every domain. */
  domain: string | null
  starred: boolean
  screening: Screening
  /** 'signal' | 'recent' | 'dim:<definition key>' */
  sort: string
  minTrl: number
  maxTrl: number
  /** 0 = all time. */
  withinDays: number
  /** 0 = no cutoff. */
  minScore: number
  /** 1-based. */
  page: number
}

export const DEFAULT_STATE: BrowseState = {
  q: '',
  domain: null,
  starred: false,
  screening: 'passed',
  sort: 'signal',
  minTrl: 1,
  maxTrl: 9,
  withinDays: 0,
  minScore: 0,
  page: 1,
}

const SORT_RE = /^(signal|recent|dim:[a-z0-9_]+)$/

function int(raw: string | undefined, { min, max }: { min: number; max: number }): number | null {
  if (raw === undefined || !/^\d+$/.test(raw)) return null
  const n = Number(raw)
  return n >= min && n <= max ? n : null
}

/** The state a URL's params describe; anything unusable takes its default. */
export function stateFrom(
  params: Record<string, string | string[] | undefined>,
  domains: readonly { id: string }[],
): BrowseState {
  const one = (key: string): string | undefined => {
    const v = params[key]
    return Array.isArray(v) ? v[0] : v
  }
  const domain = one('domain')
  const [minRaw, maxRaw] = (one('trl') ?? '').split('-')
  let minTrl = int(minRaw, { min: 1, max: 9 }) ?? 1
  let maxTrl = int(maxRaw, { min: 1, max: 9 }) ?? 9
  if (minTrl > maxTrl) [minTrl, maxTrl] = [1, 9]
  const screening = one('screening')
  const sort = one('sort') ?? ''
  return {
    q: (one('q') ?? '').trim(),
    domain: domain && domains.some((d) => d.id === domain) ? domain : null,
    starred: one('starred') === '1',
    screening: SCREENINGS.includes(screening as Screening) ? (screening as Screening) : 'passed',
    sort: SORT_RE.test(sort) ? sort : 'signal',
    minTrl,
    maxTrl,
    withinDays: int(one('days'), { min: 0, max: 3650 }) ?? 0,
    minScore: int(one('score'), { min: 0, max: 100_000 }) ?? 0,
    page: int(one('page'), { min: 1, max: 100_000 }) ?? 1,
  }
}

/** The query for a state, defaults omitted so the plain URL stays clean. */
export function searchOf(state: BrowseState): string {
  const q = new URLSearchParams()
  if (state.q) q.set('q', state.q)
  if (state.domain) q.set('domain', state.domain)
  if (state.starred) q.set('starred', '1')
  if (state.screening !== 'passed') q.set('screening', state.screening)
  if (state.sort !== 'signal') q.set('sort', state.sort)
  if (state.minTrl > 1 || state.maxTrl < 9) q.set('trl', `${state.minTrl}-${state.maxTrl}`)
  if (state.withinDays > 0) q.set('days', String(state.withinDays))
  if (state.minScore > 0) q.set('score', String(state.minScore))
  if (state.page > 1) q.set('page', String(state.page))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** What the BFF is asked for: the page's controls in the list's vocabulary. */
export function toPapersQuery(state: BrowseState): PapersQuery {
  return {
    page: state.page,
    page_size: PER_PAGE,
    screening: state.screening,
    ordering:
      state.sort === 'signal'
        ? '-signal_score'
        : state.sort === 'recent'
          ? '-created_at'
          : `-${state.sort}`,
    search: state.q || undefined,
    workspace_id: state.domain ?? undefined,
    starred: state.starred ? '1' : '0',
    min_score: state.minScore,
    min_trl: state.minTrl,
    max_trl: state.maxTrl,
    within_days: state.withinDays,
  }
}

/** The BFF path for a state — one fetch per distinct key. */
export function listPath(state: BrowseState): string {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(toPapersQuery(state))) {
    if (value === undefined) continue
    q.set(key, String(value))
  }
  return `/bff/papers?${q.toString()}`
}

/** A stable identity for a state: equal states, equal keys. */
export function keyOf(state: BrowseState): string {
  return listPath(state)
}

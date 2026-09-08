/**
 * The Papers page's filters, sort and rail facets over a corpus — pure, so
 * the BFF applies them per page and bun tests pin every rule. The order is
 * the page's own: relevance is ranked over the whole corpus (the matcher's
 * relaxed fallback fires on "strict found nothing", corpus-wide), every
 * filter but screening narrows, screening narrows last so the hint can say
 * what it alone hid, and the ordering puts relevance first only when the
 * reader has not chosen a sort of their own.
 */
import { isPassed } from '@/lib/papers/map'
import {
  byValueAsc,
  byValueDesc,
  dimensionByKey,
  numericDefinitions,
  trlDimension,
  unionDefinitions,
} from '@/lib/papers/select'
import type { ScoredPaper, WorkspaceSummary } from '@/lib/papers/types'
import { parseQuery, rankAll } from '@/lib/search/match'
import type { PapersFacets, PapersQuery } from './schema'

export interface Corpus {
  workspaces: WorkspaceSummary[]
  papers: ScoredPaper[]
}

const DAY_MS = 86_400_000

/** An ISO instant as a number; DRF omits the fraction at zero microseconds, so strings do not sort. */
const at = (iso: string): number => Date.parse(iso)

/** The newest ingest time in the corpus, or null when empty. */
export function newestOf(papers: readonly ScoredPaper[]): string | null {
  let newest: ScoredPaper | null = null
  for (const p of papers)
    if (newest === null || at(p.created_at) > at(newest.created_at)) newest = p
  return newest?.created_at ?? null
}

export function hasTrl(papers: readonly ScoredPaper[]): boolean {
  return papers.some((p) => {
    const trl = trlDimension(p)
    return trl !== undefined && trl.value !== null
  })
}

/** The rail's facets that do not depend on the query. */
export function corpusFacets(
  corpus: Corpus,
  starred: ReadonlySet<string>,
): Omit<PapersFacets, 'hidden_by_screening' | 'truncated'> {
  const { papers, workspaces } = corpus
  return {
    total: papers.length,
    // The score slider spans 0–100 unless a workspace formula scores higher.
    score_ceiling: Math.max(
      100,
      Math.ceil(papers.reduce((m, p) => Math.max(m, p.signal_score ?? 0), 0)),
    ),
    newest: newestOf(papers),
    has_trl: hasTrl(papers),
    // The same key once, however many domains define it; TRL has its own control.
    dimension_sorts: numericDefinitions({ definitions: unionDefinitions(workspaces) }, papers)
      .filter((d) => !d.is_trl)
      .map((d) => ({ key: d.key, name: d.name })),
    starred_count: papers.reduce((n, p) => n + (starred.has(p.id) ? 1 : 0), 0),
  }
}

/** A ranked relevance (higher first), then the reader's ordering. */
export function orderRows(
  rows: readonly ScoredPaper[],
  ordering: string,
  relevance?: ReadonlyMap<string, number>,
): ScoredPaper[] {
  const desc = ordering.startsWith('-')
  const key = desc ? ordering.slice(1) : ordering
  const value = (p: ScoredPaper): number | null =>
    key === 'signal_score' ? p.signal_score : (dimensionByKey(p, key.slice(4))?.value ?? null)
  const byKey = (a: ScoredPaper, b: ScoredPaper): number => {
    if (key === 'created_at') {
      const d = at(a.created_at) - at(b.created_at)
      return desc ? -d : d
    }
    return desc ? byValueDesc(value(a), value(b)) : byValueAsc(value(a), value(b))
  }
  const sorted = [...rows]
  sorted.sort((a, b) => {
    // A search reorders the default sort by relevance; an explicit sort only filters.
    if (relevance && ordering === '-signal_score') {
      const d = (relevance.get(b.id) ?? 0) - (relevance.get(a.id) ?? 0)
      if (d !== 0) return d
    }
    return byKey(a, b)
  })
  return sorted
}

export function matchesScreening(paper: ScoredPaper, screening: PapersQuery['screening']) {
  if (screening === 'all') return true
  if (screening === 'passed') return isPassed(paper.screening_status)
  return paper.screening_status === screening
}

/** The page's rows for a query, unpaginated, and what screening alone is hiding. */
export function applyPapersQuery(
  corpus: Corpus,
  query: PapersQuery,
  starred: ReadonlySet<string>,
): { rows: ScoredPaper[]; hiddenByScreening: number } {
  const { papers } = corpus
  const search = query.search?.trim() ?? ''
  const parsed = search ? parseQuery(search) : null
  const searching = parsed !== null && parsed.intent.kind !== 'empty'
  const relevance = new Map<string, number>(
    searching ? rankAll(papers, parsed).map(({ paper, hit }) => [paper.id, hit.score]) : [],
  )
  const trlWindowed = hasTrl(papers) && (query.min_trl > 1 || query.max_trl < 9)
  // The ingested window counts back from the newest paper, not wall clock, so
  // "last 24 hours" is the freshest drop even in a corpus not refreshed today.
  const newest = newestOf(papers)
  const cutoff =
    query.within_days > 0 && newest !== null ? at(newest) - query.within_days * DAY_MS : null

  const passesExceptScreening = (p: ScoredPaper): boolean => {
    if (query.workspace_id && p.workspace_id !== query.workspace_id) return false
    if (query.starred === '1' && !starred.has(p.id)) return false
    if (trlWindowed) {
      const trl = trlDimension(p)?.value ?? null
      if (trl === null || trl < query.min_trl || trl > query.max_trl) return false
    }
    if (cutoff !== null && at(p.created_at) < cutoff) return false
    if (query.min_score > 0 && (p.signal_score === null || p.signal_score < query.min_score))
      return false
    if (searching && !relevance.has(p.id)) return false
    return true
  }
  const candidates = papers.filter(passesExceptScreening)
  const kept = candidates.filter((p) => matchesScreening(p, query.screening))
  return {
    rows: orderRows(kept, query.ordering, searching ? relevance : undefined),
    hiddenByScreening: searching ? candidates.length - kept.length : 0,
  }
}

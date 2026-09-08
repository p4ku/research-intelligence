import type { Edition } from '@/lib/bff/briefings/schema'
import { runClock } from '@/lib/bff/pipeline-runs/clock'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import type { Lang, T } from '@/lib/i18n'
import { paperHref } from '@/lib/papers/href'
import type { WorkspaceSummary } from '@/lib/papers/types'
import { clockStamp, formatAuthors, formatDay, periodLabel } from '../dashboard/format'
import type { HomeBrief } from '../dashboard/ledger'
import { editionHref } from './format'
import { domainScope } from './scope'

/**
 * The archive's rows, filters and pages — pure, so the page composes them on
 * the server, the ledger filters them on the client, and bun tests both.
 * An edition is the row; its run (joined by id) supplies the period and the
 * counters Home shows, so the two screens never disagree. A run that briefed
 * nothing has no briefing to open, so it is not a row at all — here or on
 * Home, which asks `hasBriefing` too.
 */

/** The spec's page size. */
export const PER_PAGE = 20
/** How many of a briefing's strongest papers the disclosure lists (as on Home). */
export const TOP = 3

export interface ArchiveRow {
  /** The run that produced the edition — the star's id and the row's key. */
  id: string
  workspaceId: string
  domain: string
  /** The newest completed run across the user's domains. */
  current: boolean
  /** The search window, already worded; the edition's day when its run is unknown. */
  period: string
  /** The completion day, already worded. */
  generated: string
  /** "12:03 UTC" when the domain briefed more than once that day, so the rows read apart; null otherwise. */
  stamp: string | null
  screened: number
  included: number
  brief: HomeBrief
}

export interface ArchiveState {
  /** A workspace id, or null for every domain. */
  domain: string | null
  starred: boolean
  /** 1-based. */
  page: number
}

// The one run clock (lib/bff/pipeline-runs/clock.ts): Home's order and
// `editionFor` keep it too, so "Current" is the same run everywhere.
const when = runClock

/**
 * The instant a briefing was published: its run's completion, else the
 * edition's own stamp, else the run's start (a completed run can lack
 * `completed_at`). Null only for an edition with no run and no stamp.
 */
export function briefingClock(
  e: Pick<Edition, 'generated_at'>,
  run?: Pick<PipelineRun, 'completed_at' | 'started_at'> | null,
): string | null {
  return run?.completed_at ?? e.generated_at ?? run?.started_at ?? null
}

/** The (domain, day) a briefing is listed under — the day its Generated cell prints. */
export function briefingDay(
  e: Pick<Edition, 'workspace_id' | 'date' | 'generated_at'>,
  run?: Pick<PipelineRun, 'completed_at' | 'started_at'> | null,
): string {
  return `${e.workspace_id}|${(briefingClock(e, run) ?? e.date).slice(0, 10)}`
}

/**
 * How many briefings each (domain, day) holds, over every edition that is a
 * row — the rule both ledgers stamp by, so a run reads the same on Home and
 * in the archive. Counted over the whole list, never a page or a window: a
 * row's name must not depend on where it landed.
 */
export function briefingsPerDay(
  editions: readonly Pick<
    Edition,
    'run_id' | 'workspace_id' | 'date' | 'generated_at' | 'papers' | 'funnel'
  >[],
  runs: ReadonlyMap<string, PipelineRun>,
  capped: boolean,
): Map<string, number> {
  const perDay = new Map<string, number>()
  for (const e of editions) {
    const run = runs.get(e.run_id)
    const included = run?.total_papers_passed_screening ?? e.funnel.passed_screening
    if (!hasBriefing(included, e, capped)) continue
    const key = briefingDay(e, run)
    perDay.set(key, (perDay.get(key) ?? 0) + 1)
  }
  return perDay
}

/**
 * The clock a row carries when its (domain, day) holds more than one
 * briefing — "12:03 UTC" — so two rows that would otherwise read the same
 * are told apart. Null for a day with one briefing, or with no instant.
 */
export function stampFor(
  e: Pick<Edition, 'workspace_id' | 'date' | 'generated_at'>,
  run: Pick<PipelineRun, 'completed_at' | 'started_at'> | null | undefined,
  perDay: ReadonlyMap<string, number>,
): string | null {
  if ((perDay.get(briefingDay(e, run)) ?? 0) < 2) return null
  const at = briefingClock(e, run)
  return at ? clockStamp(at) : null
}

/**
 * Whether a completed run has a briefing to open. It does not when nothing
 * cleared screening, when no edition was composed for it (its domain's
 * corpus could not be read), or when the edition holds none of the papers
 * the run passed. Past the corpus cap an edition with no papers is
 * unknowable, not empty, so it still counts: its page says what is on file.
 * Home's Recent Briefings and the archive both ask this, so neither lists a
 * run the other would leave out.
 */
export function hasBriefing(
  included: number,
  edition: Pick<Edition, 'papers'> | null,
  capped: boolean,
): boolean {
  if (included === 0 || !edition) return false
  return edition.papers.length > 0 || capped
}

/** The newest completed run — the same rule Home uses for "Current". */
export function currentRunId(runs: PipelineRun[]): string | null {
  let best: PipelineRun | null = null
  for (const run of runs) {
    if (run.status !== 'completed') continue
    if (!best || when(run) > when(best)) best = run
  }
  return best?.id ?? null
}

export function composeRows({
  editions,
  runs,
  domains,
  t,
  lang,
  capped = false,
}: {
  /** Newest first, as the service returns them. */
  editions: Edition[]
  runs: PipelineRun[]
  /** Domain names by workspace id. */
  domains: Record<string, string>
  t: T
  lang: Lang
  /** The corpus cap dropped older papers: an edition with none is unknowable, not empty. */
  capped?: boolean
}): ArchiveRow[] {
  const byId = new Map(runs.map((run) => [run.id, run]))
  // If the newest completed run has no edition (its corpus could not be
  // read) no row is Current.
  const currentId = currentRunId(runs)
  const perDay = briefingsPerDay(editions, byId, capped)
  const rows: ArchiveRow[] = []
  for (const e of editions) {
    const run = byId.get(e.run_id)
    const screened = run?.total_papers_fetched ?? e.funnel.fetched
    const included = run?.total_papers_passed_screening ?? e.funnel.passed_screening
    // Nothing to open: the archive leaves the run out (and, as on Home, it
    // is never Current).
    if (!hasBriefing(included, e, capped)) continue
    rows.push({
      id: e.run_id,
      workspaceId: e.workspace_id,
      domain: domains[e.workspace_id] ?? run?.workspace_name ?? '—',
      current: e.run_id === currentId,
      period: run ? periodLabel(run, t, lang) : formatDay(e.date, lang),
      generated: formatDay(briefingClock(e, run) ?? e.date, lang),
      stamp: stampFor(e, run, perDay),
      screened,
      included,
      brief: {
        href: editionHref(e.date, e.workspace_id, { runId: e.run_id }),
        inBrief: e.in_brief,
        screened,
        included,
        top: e.papers.slice(0, TOP).map((p) => ({
          id: p.id,
          href: paperHref(p.id, { runId: e.run_id }),
          title: p.title,
          authors: formatAuthors(p.authors),
          score: p.signal_score,
        })),
      },
    })
  }
  return rows
}

/** The domain and Starred filters, applied to the whole archive before paging. */
export function filterRows(
  rows: ArchiveRow[],
  state: Pick<ArchiveState, 'domain' | 'starred'>,
  starredIds: ReadonlySet<string>,
): ArchiveRow[] {
  return rows.filter(
    (row) =>
      (state.domain === null || row.workspaceId === state.domain) &&
      (!state.starred || starredIds.has(row.id)),
  )
}

/** One page of a list; `page` comes back clamped so a stale URL still renders. */
export function paginate<Item>(
  items: Item[],
  page: number,
  per = PER_PAGE,
): { items: Item[]; page: number; pageCount: number } {
  const pageCount = Math.max(1, Math.ceil(items.length / per))
  const current = Math.min(Math.max(1, page), pageCount)
  return { items: items.slice((current - 1) * per, current * per), page: current, pageCount }
}

/** The ledger's state from the URL's query. Anything unusable is the default. */
export function stateFrom(
  params: { domain?: string; starred?: string; page?: string },
  all: Pick<WorkspaceSummary, 'id'>[],
): ArchiveState {
  const page = /^\d+$/.test(params.page ?? '') ? Number(params.page) : 0
  return {
    domain: domainScope(all, params.domain) ?? null,
    starred: params.starred === '1',
    page: page > 0 ? page : 1,
  }
}

/** The query for a state, defaults omitted so the plain URL stays clean. */
export function searchOf(state: ArchiveState): string {
  const q = new URLSearchParams()
  if (state.domain) q.set('domain', state.domain)
  if (state.starred) q.set('starred', '1')
  if (state.page > 1) q.set('page', String(state.page))
  const s = q.toString()
  return s ? `?${s}` : ''
}

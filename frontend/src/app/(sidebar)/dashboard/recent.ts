import type { Edition } from '@/lib/bff/briefings/schema'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { hasBriefing } from '../briefing/rows'

/**
 * Which runs Home's Recent Briefings lists, and which runs its live refresh
 * watches — pure, so data.ts composes them on the server and bun tests them.
 */

/** At most this many briefings in Recent Briefings, newest first. */
export const RECENT = 5

/**
 * How many runs, newest first, the in-flight set is drawn from — on the
 * server for the render and in the browser for each poll. One window on
 * both sides, so the two can never disagree about which runs are in flight
 * (a disagreement would refresh the page into the same state, and the
 * refresh guard would never release).
 */
export const POLL_RUNS = 50

export interface RecentBriefing {
  run: PipelineRun
  /** The run's edition; null while it is still processing or after it failed. */
  edition: Edition | null
}

const inFlight = (run: Pick<PipelineRun, 'status'>) =>
  run.status === 'running' || run.status === 'pending'
const failed = (run: Pick<PipelineRun, 'status'>) =>
  run.status === 'failed' || run.status === 'aborted'

/**
 * The newest RECENT briefings across the user's domains — the first page of
 * the archive — with the runs that are not briefings yet kept in their
 * place: a run in flight (there is at most one at a time) and, per domain,
 * its latest failure until that domain briefs again, so Retry is offered
 * where it is still wanted and an old failure does not outlive its fix.
 * Only briefings count toward RECENT; the others ride along above the
 * cut, so a run of failures cannot crowd the briefings out. A completed
 * run that briefed nothing is not a briefing and is not a row — the
 * archive applies the same rule, so the two screens list the same runs.
 */
export function selectRecent(
  /** Newest first. */
  runs: PipelineRun[],
  /** Every edition the user can see, by run id. */
  editions: ReadonlyMap<string, Edition>,
  /** The corpus cap dropped older papers: an edition with none is unknowable, not empty. */
  capped: boolean,
): RecentBriefing[] {
  const rows: RecentBriefing[] = []
  // Domains whose story is told: a briefing, or the failure that stands in for one.
  const settled = new Set<string>()
  let briefed = 0
  for (const run of runs) {
    if (briefed === RECENT) break
    if (inFlight(run)) {
      rows.push({ run, edition: null })
    } else if (failed(run)) {
      if (settled.has(run.workspace_id)) continue
      settled.add(run.workspace_id)
      rows.push({ run, edition: null })
    } else if (run.status === 'completed') {
      const edition = editions.get(run.id) ?? null
      if (!hasBriefing(run.total_papers_passed_screening, edition, capped)) continue
      settled.add(run.workspace_id)
      rows.push({ run, edition })
      briefed++
    }
  }
  return rows
}

/** The ids of the runs in flight within the poll window, sorted, so two sets compare as strings. */
export function inFlightIds(runs: Pick<PipelineRun, 'id' | 'status'>[]): string[] {
  return runs
    .slice(0, POLL_RUNS)
    .filter(inFlight)
    .map((run) => run.id)
    .sort()
}

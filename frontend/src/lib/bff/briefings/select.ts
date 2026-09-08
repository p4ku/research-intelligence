/**
 * Which edition a permalink names, and which of several is newest.
 * Editions are one per completed run, so a day can hold several in one
 * domain; the URL carries the run id to pick one. One clock throughout:
 * an edition was published when its run completed. Pure, so the service,
 * the pages and the tests share the rules.
 */
import type { PipelineRun } from '../pipeline-runs/schema'
import type { Edition } from './schema'

/**
 * The day an edition is addressed by: its run's completion day (UTC), or
 * the trigger day while the run has none. The one rule behind every
 * `/briefing/<date>` — the service composes with it, Home and the paper
 * page build links with it.
 */
export function editionDate(run: Pick<PipelineRun, 'completed_at' | 'run_date'>): string {
  return run.completed_at ? run.completed_at.slice(0, 10) : run.run_date
}

/** When an edition was published: its run's completion, or failing that its day. */
export const when = (e: Pick<Edition, 'date' | 'generated_at'>) =>
  e.generated_at ?? `${e.date}T00:00:00Z`

/** Newest first, by publication — a sort order every list of editions shares. */
export function byNewest(
  a: Pick<Edition, 'date' | 'generated_at'>,
  b: Pick<Edition, 'date' | 'generated_at'>,
): number {
  return when(b).localeCompare(when(a))
}

/**
 * The newest edition of a list by the clock, not by position: one caller
 * lists editions in run-start order and another in completion order, and a
 * long run can start first and finish last. Null for an empty list.
 */
export function newest<E extends Pick<Edition, 'date' | 'generated_at'>>(
  editions: readonly E[],
): E | null {
  let best: E | null = null
  for (const e of editions) if (!best || when(e) > when(best)) best = e
  return best
}

/**
 * The edition of `date` for `runId` when one of the day's holds it;
 * otherwise the day's newest edition by completion time — what a link
 * without a run, or with one that has since gone, means. Null when nothing
 * was published that day.
 */
export function editionFor<E extends Pick<Edition, 'date' | 'run_id' | 'generated_at'>>(
  editions: readonly E[],
  date: string,
  runId?: string,
): E | null {
  const ofDay = editions.filter((e) => e.date === date)
  if (runId) {
    const exact = ofDay.find((e) => e.run_id === runId)
    if (exact) return exact
  }
  return newest(ofDay)
}

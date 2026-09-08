/**
 * Which edition a permalink names. Editions are one per completed run, so a
 * day can hold several in one domain; the URL carries the run id to pick
 * one. Pure, so the service and the tests share the rule.
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
const when = (e: Pick<Edition, 'date' | 'generated_at'>) => e.generated_at ?? `${e.date}T00:00:00Z`

/**
 * The edition of `date` for `runId` when one of the day's holds it;
 * otherwise the day's newest edition by completion time — what a link
 * without a run, or with one that has since gone, means. Newest by the
 * clock, not by position: one caller lists editions in run-start order and
 * another in completion order, and a long run can start first and finish
 * last. Null when nothing was published that day.
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
  let newest: E | null = null
  for (const e of ofDay) if (!newest || when(e) > when(newest)) newest = e
  return newest
}

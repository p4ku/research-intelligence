/**
 * The one clock every list of runs keeps: a run's last act — its completion,
 * or its start while it is still in flight, or its trigger day when it has
 * neither. A briefing is published when its run completes, so this is also
 * the order editions take (../briefings/select.ts), and "Current" is the
 * same run on Home and in the archive. The service sorts by it once, so the
 * page a render windows and the page a poll fetches hold the same runs. Pure.
 */
import type { PipelineRun } from './schema'

export const runClock = (run: Pick<PipelineRun, 'completed_at' | 'started_at' | 'run_date'>) =>
  run.completed_at ?? run.started_at ?? run.run_date

/** Newest first by the run clock. */
export function byRunClock(
  a: Pick<PipelineRun, 'completed_at' | 'started_at' | 'run_date'>,
  b: Pick<PipelineRun, 'completed_at' | 'started_at' | 'run_date'>,
): number {
  return runClock(b).localeCompare(runClock(a))
}

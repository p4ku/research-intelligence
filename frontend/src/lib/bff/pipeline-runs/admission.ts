/**
 * Whether a start would be admitted: the per-domain cap on runs in flight
 * and the rule that one search window runs once at a time. Django is the
 * authority (research_intelligence/services/run_admission.py answers 409
 * with `run_limit_reached` / `duplicate_run`); this mirror lets the start
 * route refuse a stale tab without a round-trip and lets Home's form show
 * why Start is off before anyone clicks it. Pure — client-importable.
 */
import type { PipelineRun, StartRun } from './schema'

/** Django's MAX_CONCURRENT_RUNS_PER_WORKSPACE default. */
export const MAX_IN_FLIGHT_PER_DOMAIN = 5

/** The slice of a run the admission rule reads — what Home hands its form. */
export type InFlightRun = Pick<
  PipelineRun,
  | 'id'
  | 'workspace_id'
  | 'workspace_name'
  | 'status'
  | 'period_start'
  | 'period_end'
  | 'lookback_days'
>

/** A run that holds one of its domain's slots (Django's `paused` arrives as `pending`). */
export const isInFlight = (run: Pick<PipelineRun, 'status'>) =>
  run.status === 'running' || run.status === 'pending'

type Window = readonly [string | null, string | null, number | null]

/** Dates win over the lookback, as in the engine; a window with neither is unknown. */
function windowOf(run: Pick<InFlightRun, 'period_start' | 'period_end' | 'lookback_days'>): Window {
  if (run.period_start || run.period_end) return [run.period_start, run.period_end, null]
  return [null, null, run.lookback_days]
}

function inputWindow(input: StartRun): Window {
  const start = input.start_date ?? null
  const end = input.end_date ?? null
  if (start || end) return [start, end, null]
  return [null, null, input.lookback_days ?? null]
}

/** True when the run searched the window the start asks for; an unknown window matches nothing. */
export function sameWindow(
  run: Pick<InFlightRun, 'period_start' | 'period_end' | 'lookback_days'>,
  input: StartRun,
): boolean {
  const wanted = inputWindow(input)
  if (wanted.every((part) => part === null)) return false
  const had = windowOf(run)
  return had[0] === wanted[0] && had[1] === wanted[1] && had[2] === wanted[2]
}

/** The runs in flight for one domain. */
export function inFlightFor<R extends InFlightRun>(runs: readonly R[], workspaceId: string): R[] {
  return runs.filter((run) => run.workspace_id === workspaceId && isInFlight(run))
}

export type Admission =
  | { ok: true; count: number }
  | { ok: false; reason: 'cap' | 'duplicate'; domain: string; count: number; run: InFlightRun }

/**
 * The verdict for a start, from the runs the page (or the route) holds.
 * `count` is how many runs the domain has in flight before this start.
 */
export function admission(runs: readonly InFlightRun[], input: StartRun): Admission {
  const mine = inFlightFor(runs, input.workspace_id)
  const count = mine.length
  if (count >= MAX_IN_FLIGHT_PER_DOMAIN) {
    return { ok: false, reason: 'cap', domain: mine[0].workspace_name, count, run: mine[0] }
  }
  const twin = mine.find((run) => sameWindow(run, input))
  if (twin) return { ok: false, reason: 'duplicate', domain: twin.workspace_name, count, run: twin }
  return { ok: true, count }
}

/** The sentence Django would answer with — the route's 409 detail. */
export function refusalDetail(verdict: Extract<Admission, { ok: false }>): string {
  return verdict.reason === 'cap'
    ? `${verdict.count} of ${MAX_IN_FLIGHT_PER_DOMAIN} runs in progress for ${verdict.domain}. Wait for one to finish.`
    : `${verdict.domain} is already running this search window.`
}

/**
 * The window a run searched, read from Django's `configuration_override`.
 * The engine accepts explicit `start_date`/`end_date` (ISO strings, possibly
 * with a time part) or a relative `n_last_days`; older runs carry neither.
 * Pure — unit-tested.
 */

export interface RunPeriod {
  /** YYYY-MM-DD, or null when the run had no explicit start. */
  period_start: string | null
  /** YYYY-MM-DD, or null when the run had no explicit end. */
  period_end: string | null
  /** The relative window, when the run was given one instead of dates. */
  lookback_days: number | null
}

export interface PeriodConfig {
  start_date?: string | null
  end_date?: string | null
  n_last_days?: number | null
  limit?: number | null
  query_prefix?: string | null
}

/** True when the run's inputs are just a domain and a window — what Home can resend. */
export function isRetryable(cfg: PeriodConfig | null | undefined): boolean {
  return !(typeof cfg?.limit === 'number') && !cfg?.query_prefix
}

/** The first ten characters when they read as a calendar date; else null. */
function isoDay(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null
  const day = value.slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : null
}

export function runPeriod(cfg: PeriodConfig | null | undefined): RunPeriod {
  const period_start = isoDay(cfg?.start_date)
  const period_end = isoDay(cfg?.end_date)
  const days = cfg?.n_last_days
  // Explicit dates win over the relative window, as they do in the engine.
  const lookback_days =
    !period_start && !period_end && typeof days === 'number' && Number.isInteger(days) && days > 0
      ? days
      : null
  return { period_start, period_end, lookback_days }
}

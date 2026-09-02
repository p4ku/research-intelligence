/**
 * Catch-to-result for fetches whose failure is a UI state, not a crash.
 * The cure for catch-to-empty boolean blindness (error-UX audit #2): the
 * caller gets `{ok: false, problem}` and can tell an outage from a genuine
 * absence, instead of both collapsing into `[]`/null. Pure.
 */
import { ProblemError, type Problem } from './problem'

export type Result<T> = { ok: true; value: T } | { ok: false; problem: Problem }

/**
 * Resolve `work` into a Result. A 401 still throws (the caller's `forPage`
 * routes it to logout), as does anything that isn't a ProblemError — a
 * programming error should crash the boundary, not become a notice.
 */
export async function problemResult<T>(work: Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, value: await work }
  } catch (error) {
    if (error instanceof ProblemError && error.problem.status !== 401) {
      // The swallowed problem stays visible to operators.
      console.error('[bff] degraded to result:', error.problem)
      return { ok: false, problem: error.problem }
    }
    throw error
  }
}

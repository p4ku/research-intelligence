/**
 * How a scorecard read is addressed: the query it sends and the list it reads
 * back. Pure, so both are testable without the server-only service.
 *
 * `GET /api/workspaces/{id}/scorecard/` answers with the whole workspace
 * unless it is narrowed, and answers twice over unless it is told not to
 * (backend `research_intelligence/services/scorecard_service.py`). A scorecard
 * row weighs ~39 KB on production data — most of it a dimension's
 * `response_schema` — so both parameters are worth a great deal on a briefing.
 */

/** The papers a scorecard read is for. */
export interface ScorecardScope {
  /** One run's papers. */
  runId?: string
  /**
   * `passed` narrows that run to the papers a briefing lists. Django's
   * `run_id` filters on `metrics__pipeline_run`, so on its own it matches
   * every paper the run *screened* — 771 where the briefing shows 23.
   */
  screening?: 'passed'
}

/**
 * The query string for a scorecard read, without its leading `?`. Extra
 * parameters (paging) come first, in the caller's order, so a URL reads the
 * way the endpoint's own docs write it.
 *
 * `results_only=true` is always sent: without it the response carries the same
 * list under both `papers` and `results`, and `scorecardRows` reads either.
 */
export function scorecardQuery(scope?: ScorecardScope, ...extra: string[]): string {
  const params = [...extra, 'results_only=true']
  if (scope?.runId) params.push(`run_id=${encodeURIComponent(scope.runId)}`)
  if (scope?.screening) params.push(`screening=${scope.screening}`)
  return params.join('&')
}

/**
 * The rows of a scorecard response, from whichever key carries them: a backend
 * that honoured `results_only` sends `results` alone, one that did not sends
 * both, and one that predates the parameter sends `papers` alone. Neither key
 * is no rows, never a throw — an empty scorecard is a legitimate answer.
 */
export function scorecardRows<T>(body: { papers?: T[]; results?: T[] }): T[] {
  return body.papers ?? body.results ?? []
}

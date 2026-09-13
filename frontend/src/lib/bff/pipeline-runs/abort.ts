/**
 * Django's refusals of an abort, re-typed. Pure, so bun can test it
 * (service.ts imports 'server-only').
 *
 * `POST /api/pipeline-runs/{id}/abort/` answers every refusal with 400 and
 * an "Error: …" sentence in `{error}` (api/views/pipeline_runs.py `abort`
 * wraps the bare string the service layer returns). A 400 maps to
 * /problems/validation, and validation is the one problem whose `detail`
 * a reader sees verbatim — so the two known sentences become the house
 * problems they really are, and anything else becomes an upstream error.
 * No Django prose reaches the screen.
 */
import { problem, ProblemError } from '../core/problem'

/** "PipelineRun '…' is already in status 'completed'." — the run ended first. */
const ALREADY_ENDED = /already in status|cannot be aborted/i
/**
 * "Insufficient workspace permissions. Role '…' required to be one of
 * ['admin', 'manager'] …" — and, should the view's membership scoping ever
 * loosen, "Access denied. User '…' is not a member of workspace '…'."
 */
const NO_PERMISSION =
  /insufficient workspace permissions|required to be one of|access denied|not a member/i

export function abortProblem(error: unknown): unknown {
  if (!(error instanceof ProblemError) || error.problem.status !== 400) return error
  const detail = error.problem.detail ?? ''
  if (ALREADY_ENDED.test(detail)) return problem('conflict', { detail })
  if (NO_PERMISSION.test(detail)) return problem('forbidden', { detail })
  return problem('upstream-error', { detail })
}

/**
 * RFC 9457 problem details — the only error shape BFF consumers ever see.
 * Pure (no zod, no next imports): the proxy and client bundle import it, and
 * the contract scripts import modules that do.
 *
 * The slug table below is the catalogue we also ask the backend to adopt;
 * `type` stays a stable relative URI (`/problems/<slug>`).
 */

export interface Problem {
  /** Stable, relative problem type: `/problems/<slug>`. */
  type: string
  title: string
  status: number
  detail?: string
  /** The request path that produced the problem. */
  instance?: string
  /** Field errors, DRF-style: `{"field": ["message", …]}`. */
  errors?: Record<string, string[]>
  /** Which BFF source produced the response (mirrors `X-BFF-Source`). */
  source?: string
}

const CATALOG = {
  validation: { status: 400, title: 'Invalid request' },
  unauthenticated: { status: 401, title: 'Not signed in' },
  forbidden: { status: 403, title: 'Not allowed' },
  'not-found': { status: 404, title: 'Not found' },
  'method-not-allowed': { status: 405, title: 'Method not allowed' },
  conflict: { status: 409, title: 'Conflict' },
  internal: { status: 500, title: 'Internal error' },
  'not-implemented': { status: 501, title: 'Not available yet' },
  'upstream-unavailable': { status: 502, title: 'Backend unreachable' },
  'upstream-error': { status: 502, title: 'Backend error' },
  'upstream-shape': { status: 502, title: 'The data service returned an unexpected response' },
} as const

export type ProblemSlug = keyof typeof CATALOG

/** Every slug in the catalogue — problem-copy.test.ts checks copy coverage against it. */
export const PROBLEM_SLUGS = Object.keys(CATALOG) as ProblemSlug[]

/** Build a problem body without throwing (the proxy uses this directly). */
export function problemBody(slug: ProblemSlug, extra: Partial<Problem> = {}): Problem {
  const base = CATALOG[slug]
  return { type: `/problems/${slug}`, title: base.title, status: base.status, ...extra }
}

export class ProblemError extends Error {
  readonly problem: Problem

  constructor(problem: Problem) {
    super(`${problem.status} ${problem.title}${problem.detail ? `: ${problem.detail}` : ''}`)
    this.name = 'ProblemError'
    this.problem = problem
  }
}

/** Django rejected the session: the one failure that must reach the logout flow. */
export function isUnauthenticated(error: unknown): error is ProblemError {
  return error instanceof ProblemError && error.problem.status === 401
}

/** Throwable shorthand: `throw problem('not-found', { detail })`. */
export function problem(slug: ProblemSlug, extra: Partial<Problem> = {}): ProblemError {
  return new ProblemError(problemBody(slug, extra))
}

/** Any thrown value → a problem body (unknown errors become opaque 500s). */
export function asProblem(error: unknown, instance?: string): Problem {
  if (error instanceof ProblemError) {
    return { instance, ...error.problem }
  }
  return problemBody('internal', {
    instance,
    detail: process.env.NODE_ENV === 'production' ? undefined : String(error),
  })
}

export function problemResponse(body: Problem, headers?: HeadersInit): Response {
  return Response.json(body, {
    status: body.status,
    headers: { 'content-type': 'application/problem+json', ...headers },
  })
}

/**
 * Map an upstream (Django) error response onto a problem. Handles the error
 * shapes the backend uses today: `{error}`, `{detail}`, DRF field errors,
 * and plain text.
 */
export function fromUpstream(status: number, body: unknown): ProblemError {
  const detail = upstreamDetail(body)
  const errors = upstreamFieldErrors(body)
  if (status === 400) return problem('validation', { detail, errors })
  if (status === 401) return problem('unauthenticated', { detail })
  if (status === 403) return problem('forbidden', { detail })
  if (status === 404) return problem('not-found', { detail })
  if (status === 405) return problem('method-not-allowed', { detail })
  if (status === 409) return problem('conflict', { detail })
  return problem('upstream-error', {
    detail: detail ?? `The backend responded ${status}.`,
    errors,
  })
}

/** `{error}` or `{detail}` or a plain string, else undefined. */
export function upstreamDetail(body: unknown): string | undefined {
  if (typeof body === 'string' && body.trim()) return body.trim().slice(0, 500)
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    for (const key of ['error', 'detail', 'message']) {
      if (typeof record[key] === 'string') return record[key] as string
    }
  }
  return undefined
}

/** DRF field errors (`{"field": ["msg"]}`) normalised to `Record<string, string[]>`. */
export function upstreamFieldErrors(body: unknown): Record<string, string[]> | undefined {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return undefined
  const out: Record<string, string[]> = {}
  for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
    // Envelope keys, not fields: DRF's `{detail}`, the custom handler's
    // `{status_code, error, detail}`, the MCP tools' `{status: "error", error}`.
    if (key === 'error' || key === 'detail' || key === 'message' || key === 'status') continue
    if (typeof value === 'string') out[key] = [value]
    else if (Array.isArray(value) && value.every((v) => typeof v === 'string')) {
      out[key] = value as string[]
    }
  }
  return Object.keys(out).length > 0 ? out : undefined
}

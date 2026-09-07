/**
 * Problem → product copy. The one place a problem+json body becomes text a
 * user reads; render sites never print `title` or `detail` themselves.
 * `type` is the machine-stable join key (RFC 9457); `detail` is a debugging
 * aid that only `/problems/validation` may surface, because there it is
 * human-written (Django's own validation prose).
 * Client-safe: types only, no server imports.
 */
import { problemSlug, type Problem } from '@/lib/bff/core/problem'
import type { T } from '@/lib/i18n'

/**
 * English source sentence per problem slug (translated through `t`, so every
 * value needs a `de/errors.ts` entry — problem-copy.test.ts enforces both
 * directions against the CATALOG in core/problem.ts).
 */
export const PROBLEM_COPY: Record<string, string> = {
  validation: 'Check your input and try again.',
  unauthenticated: 'Your session has ended. Sign in again.',
  forbidden: "You don't have access to this.",
  'not-found': "That wasn't found. It may have been removed.",
  'method-not-allowed': 'Something went wrong. Try again.',
  conflict: 'This was changed somewhere else. Reload the page and try again.',
  internal: 'Something went wrong on our side. Try again.',
  'not-implemented': "This isn't available yet.",
  'upstream-unavailable': "The backend didn't respond. Try again in a moment.",
  'upstream-error': 'The backend had a problem. Try again in a moment.',
  'upstream-shape': 'The backend sent something unexpected. Try again in a moment.',
}

const FALLBACK = 'Something went wrong. Try again.'

/** The sentence a user should read for this problem, in the current language. */
export function problemMessage(problem: Problem | null | undefined, t: T): string {
  if (!problem) return t(FALLBACK)
  const slug = problemSlug(problem.type)
  if (slug === 'validation' && problem.detail) return problem.detail
  const copy = PROBLEM_COPY[slug]
  return t(copy ?? FALLBACK)
}

/**
 * A failed form submit → the errors map a form renders. Guarantees the
 * partition invariant: a thrown error always yields a non-empty map, so a
 * submit can never fail silently.
 *
 * Field keys only paint fields on `/problems/validation` — an
 * `upstream-shape` errors map describes the backend's response, not the
 * user's input, and must not mark a valid field invalid. Keys the form does
 * not render (DRF `non_field_errors`, zod's `(root)`) fold into `_`.
 */
export function errorsFromSubmit(
  error: unknown,
  fieldNames: readonly string[],
  t: T,
  fallback: string,
): Record<string, string> {
  const out: Record<string, string> = {}
  if (isProblemCarrier(error)) {
    const p = error.problem
    if (p.type === '/problems/validation') {
      const rest: string[] = []
      for (const [field, messages] of Object.entries(p.errors ?? {})) {
        if (fieldNames.includes(field)) out[field] = messages.join(' ')
        else rest.push(...messages)
      }
      if (rest.length > 0) out._ = rest.join(' ')
    }
    if (Object.keys(out).length === 0) out._ = problemMessage(p, t)
  } else {
    out._ = fallback
  }
  return out
}

/** Structural check so BffClientError works across module instances. */
function isProblemCarrier(error: unknown): error is { problem: Problem } {
  if (!error || typeof error !== 'object' || !('problem' in error)) return false
  const p = (error as { problem: unknown }).problem
  return (
    !!p &&
    typeof p === 'object' &&
    typeof (p as Problem).type === 'string' &&
    typeof (p as Problem).status === 'number'
  )
}

/**
 * zod parsing that fails as problem+json. Pure.
 *
 * - Request bodies / queries that fail → 400 `validation` (client's fault).
 * - Upstream responses that fail       → 502 `upstream-shape` (backend drifted
 *   from the contract; the zod issue paths land in `errors`).
 */
import * as z from 'zod'
import { problem } from './problem'

export function zodErrors(error: z.ZodError): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const issue of error.issues) {
    const path = issue.path.length > 0 ? issue.path.join('.') : '(root)'
    ;(out[path] ??= []).push(issue.message)
  }
  return out
}

export async function parseBody<T extends z.ZodType>(
  schema: T,
  request: Request,
): Promise<z.output<T>> {
  let raw: unknown
  try {
    raw = await request.json()
  } catch {
    throw problem('validation', { detail: 'The request body is not valid JSON.' })
  }
  const parsed = schema.safeParse(raw)
  if (!parsed.success) throw problem('validation', { errors: zodErrors(parsed.error) })
  return parsed.data
}

export function parseQuery<T extends z.ZodType>(schema: T, url: URL): z.output<T> {
  const raw = Object.fromEntries(url.searchParams.entries())
  const parsed = schema.safeParse(raw)
  if (!parsed.success) throw problem('validation', { errors: zodErrors(parsed.error) })
  return parsed.data
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Pages guard permalink params with this so `/papers/abc123` is a 404, not an error card. */
export function isUuid(value: string): boolean {
  return UUID_RE.test(value)
}

/**
 * Guard for values interpolated into upstream URL paths. Route params arrive
 * percent-decoded, so without this a crafted id ('../workspaces/<uuid>')
 * would retarget the Bearer-authed request after fetch normalizes the path.
 */
export function assertUuid(value: string, label = 'id'): string {
  if (!UUID_RE.test(value)) {
    throw problem('validation', { detail: `${label} must be a UUID.` })
  }
  return value
}

/** Validate data from Django against a contract/upstream schema. */
export function parseUpstream<T extends z.ZodType>(
  schema: T,
  data: unknown,
  context: string,
): z.output<T> {
  const parsed = schema.safeParse(data)
  if (!parsed.success) {
    throw problem('upstream-shape', {
      detail: `The backend's response for ${context} does not match the expected shape.`,
      errors: zodErrors(parsed.error),
    })
  }
  return parsed.data
}

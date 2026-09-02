/**
 * The one way BFF services talk to Django: `apiFetch` (Bearer from the
 * session cookie) + status mapping to problems + zod validation of the body.
 * Server-only.
 */
import 'server-only'

import { apiFetch, type ApiInit } from '@/lib/api/server'
import type * as z from 'zod'
import { fromUpstream, problem } from './problem'
import { parseUpstream } from './validate'

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

/** GET/parse helper: Django response → contract/upstream shape or a ProblemError. */
export async function django<T extends z.ZodType>(
  path: string,
  schema: T,
  init: ApiInit = {},
): Promise<z.output<T>> {
  let res: Response
  try {
    res = await apiFetch(path, init)
  } catch (error) {
    console.error('[bff] Django fetch failed:', path, error)
    throw problem('upstream-unavailable', { detail: `Django did not respond (${path}).` })
  }
  if (!res.ok) throw fromUpstream(res.status, await readBody(res))
  if (res.status === 204) return undefined as z.output<T>
  return parseUpstream(schema, await readBody(res), path)
}

/** For writes with no interesting body (e.g. DELETE) — maps errors, ignores the body. */
export async function djangoVoid(path: string, init: ApiInit = {}): Promise<void> {
  let res: Response
  try {
    res = await apiFetch(path, init)
  } catch (error) {
    console.error('[bff] Django fetch failed:', path, error)
    throw problem('upstream-unavailable', { detail: `Django did not respond (${path}).` })
  }
  if (!res.ok) throw fromUpstream(res.status, await readBody(res))
}

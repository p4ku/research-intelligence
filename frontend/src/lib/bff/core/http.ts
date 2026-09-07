/**
 * The one way BFF services talk to Django: `apiFetch` (Bearer from the
 * session cookie) + status mapping to problems + zod validation of the body.
 * Server-only.
 */
import 'server-only'

import { apiFetch, type ApiInit } from '@/lib/api/server'
import type * as z from 'zod'
import type { FetchedPage } from './drain'
import { pageSchema } from './pagination'
import { fromUpstream, problem } from './problem'
import { parseUpstream } from './validate'

async function readBody(res: Response): Promise<{ value: unknown; length: number }> {
  const text = await res.text()
  if (!text) return { value: null, length: 0 }
  try {
    return { value: JSON.parse(text) as unknown, length: text.length }
  } catch {
    return { value: text, length: text.length }
  }
}

async function fetchOk(path: string, init: ApiInit): Promise<Response> {
  let res: Response
  try {
    res = await apiFetch(path, init)
  } catch (error) {
    console.error('[bff] Django fetch failed:', path, error)
    throw problem('upstream-unavailable', { detail: `Django did not respond (${path}).` })
  }
  if (!res.ok) throw fromUpstream(res.status, (await readBody(res)).value)
  return res
}

/** GET/parse helper: Django response → contract/upstream shape or a ProblemError. */
export async function django<T extends z.ZodType>(
  path: string,
  schema: T,
  init: ApiInit = {},
): Promise<z.output<T>> {
  const res = await fetchOk(path, init)
  if (res.status === 204) return undefined as z.output<T>
  return parseUpstream(schema, (await readBody(res)).value, path)
}

/**
 * One page of a Django list, with the body's size as received — what the
 * corpus drain (./drain.ts) walks and the snapshot cache weighs. Strict about
 * the envelope: a bare array (the list ignoring `page`) is an upstream-shape
 * problem, never a silent fall back to the unbounded list.
 */
export async function djangoPage<T extends z.ZodType>(
  path: string,
  item: T,
  page: number,
  pageSize: number,
  init: ApiInit = {},
): Promise<FetchedPage<z.output<T>>> {
  const url = `${path}${path.includes('?') ? '&' : '?'}page=${page}&page_size=${pageSize}`
  const res = await fetchOk(url, init)
  const body = await readBody(res)
  return { page: parseUpstream(pageSchema(item), body.value, url), bytes: body.length }
}

/** For writes with no interesting body (e.g. DELETE) — maps errors, ignores the body. */
export async function djangoVoid(path: string, init: ApiInit = {}): Promise<void> {
  await fetchOk(path, init)
}

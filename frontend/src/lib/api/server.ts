import 'server-only'

import { ACCESS_COOKIE } from '@/lib/auth/cookies'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { backendUrl, isTransientNetworkError } from './backend-url'

// The single place the Next.js server talks to Django.
//
// Every request carries the access JWT from the httpOnly cookie as a Bearer
// header and is never cached (the data is per-user). Refresh is not handled
// here — server components cannot write cookies — it happens in
// `src/proxy.ts` before the render, so a 401 here means the session is gone.
//
// A later phase moves data access into Next route handlers under /bff/*;
// they will call these same helpers with `onUnauthorized: 'throw'`.

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message?: string,
  ) {
    super(message ?? `Backend responded ${status}`)
    this.name = 'ApiError'
  }
}

export interface ApiInit extends RequestInit {
  /** Attach the session's Bearer token (default true). */
  auth?: boolean
}

export async function apiFetch(path: string, init: ApiInit = {}): Promise<Response> {
  const { auth = true, headers, ...rest } = init
  const h = new Headers(headers)
  h.set('Accept', 'application/json')
  if (auth) {
    const token = (await cookies()).get(ACCESS_COOKIE)?.value
    if (token) h.set('Authorization', `Bearer ${token}`)
  }
  const url = `${backendUrl()}${path}`
  try {
    return await fetch(url, { ...rest, headers: h, cache: 'no-store' })
  } catch (error) {
    if (isTransientNetworkError(error)) {
      await new Promise((resolve) => setTimeout(resolve, 150))
      return await fetch(url, { ...rest, headers: h, cache: 'no-store' })
    }
    throw error
  }
}

export interface ApiJsonInit extends ApiInit {
  /** What to do on 401: send the user to the login page (default) or throw. */
  onUnauthorized?: 'redirect' | 'throw'
}

export async function apiJson<T>(path: string, init: ApiJsonInit = {}): Promise<T> {
  const { onUnauthorized = 'redirect', ...rest } = init
  const res = await apiFetch(path, rest)
  if (res.status === 401 && onUnauthorized === 'redirect') {
    redirect('/auth/logout?reason=expired')
  }
  if (!res.ok) throw new ApiError(res.status, await readBody(res))
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/** Error message from a Django error body (`{error}` or `{detail}`), else a fallback. */
export function apiErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>
    if (typeof b.error === 'string') return b.error
    if (typeof b.detail === 'string') return b.detail
  }
  return fallback
}

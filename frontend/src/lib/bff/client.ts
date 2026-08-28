/**
 * Client-side access to the BFF: JSON in/out, problem+json surfaced as
 * `BffClientError`, expired sessions routed through the logout flow.
 * Client-safe (no server imports); server components import services
 * directly instead of fetching over loopback HTTP.
 */
import type { Problem } from './core/problem'

export class BffClientError extends Error {
  readonly problem: Problem

  constructor(problem: Problem) {
    super(problem.detail ? `${problem.title}: ${problem.detail}` : problem.title)
    this.name = 'BffClientError'
    this.problem = problem
  }
}

export async function bffFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('accept', 'application/json')
  if (init.body && !headers.has('content-type')) headers.set('content-type', 'application/json')

  const res = await fetch(path, { ...init, headers })
  const contentType = res.headers.get('content-type') ?? ''

  if (contentType.includes('application/problem+json')) {
    const body = (await res.json()) as Problem
    if (body.status === 401 && typeof window !== 'undefined') {
      window.location.assign('/auth/logout?reason=expired')
    }
    throw new BffClientError(body)
  }
  if (res.status === 204) return undefined as T
  if (!res.ok || !contentType.includes('json')) {
    throw new BffClientError({
      type: '/problems/internal',
      title: `Unexpected response (${res.status})`,
      status: res.status,
      instance: path,
    })
  }
  return (await res.json()) as T
}

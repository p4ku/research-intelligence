/**
 * Wrapper for every `/bff` route handler: same-origin guard on writes,
 * problem+json for anything thrown, `X-BFF-Source` on every response.
 * Server-only.
 */
import 'server-only'

import { isSameOrigin } from '@/lib/auth/same-origin'
import type { NextRequest } from 'next/server'
import { asProblem, problem, ProblemError, problemResponse } from './problem'
import { sourceOf, type ResourceName, type Source } from './source'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export type BffRouteContext = { params: Promise<Record<string, string>> }
export type BffRouteHandler = (request: NextRequest, ctx: BffRouteContext) => Promise<Response>

/**
 * `resource` names the registry entry whose active source stamps the
 * response; pass `null` for routes without one (e.g. /bff/status).
 */
export function bff(resource: ResourceName | null, handler: BffRouteHandler): BffRouteHandler {
  return async (request, ctx) => {
    const source: Source | null = resource ? sourceOf(resource) : null
    try {
      if (!SAFE_METHODS.has(request.method) && !isSameOrigin(request)) {
        throw problem('forbidden', { detail: 'Cross-origin writes are not allowed.' })
      }
      const res = await handler(request, ctx)
      if (source) res.headers.set('x-bff-source', source)
      if (!res.headers.has('cache-control')) res.headers.set('cache-control', 'no-store')
      return res
    } catch (error) {
      const body = asProblem(error, request.nextUrl.pathname)
      // A 4xx is the caller's to read in the response; a 5xx is ours (or
      // the backend's) to explain, so it leaves a line in the platform log
      // (501 is a route's normal answer for what it does not do yet). The
      // field errors are the only thing a shape mismatch has to say, and
      // the unknown kind carries the original error: in production the body
      // hides it, and this is the one place it is still in hand.
      if (body.status >= 500 && body.status !== 501) {
        const where = `${request.method} ${request.nextUrl.pathname}${request.nextUrl.search}`
        const detail = body.detail ? `: ${body.detail.slice(0, 500)}` : ''
        console.error(
          `[bff] ${where} → ${body.status} ${body.type}${detail}`,
          ...(body.errors ? [body.errors] : []),
          ...(error instanceof ProblemError ? [] : [error]),
        )
      }
      return problemResponse(
        source ? { ...body, source } : body,
        source ? { 'x-bff-source': source } : undefined,
      )
    }
  }
}

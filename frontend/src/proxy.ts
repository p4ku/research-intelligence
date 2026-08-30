import { backendUrl } from '@/lib/api/backend-url'
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  authCookieOptions,
  clearAuthCookies,
} from '@/lib/auth/cookies'
import { secondsUntilExpiry } from '@/lib/auth/jwt'
import { problemBody } from '@/lib/bff/core/problem'
import { NextResponse, type NextRequest } from 'next/server'

// Two jobs, in this order:
//
// 1. Reverse-proxy the backend's URL prefixes to Django / FastMCP. In
//    production Cloud Foundry's router sends these to the backend apps before
//    we see them, but it occasionally leaks them here, and locally this is
//    the only path from the browser to the API (same origin, no CORS).
// 2. Gate the app on the session cookies and refresh the access token before
//    it expires. This is the only place that both sees every navigation and
//    can write cookies, so refresh lives here rather than in the pages.

const BACKEND_PREFIX =
  /^\/(admin|api|mcp|docs|swagger|redoc|schema|static|media|health|sse|messages)(\/|$)/

const PUBLIC_ROUTES = [
  /^\/$/,
  /^\/auth(\/|$)/,
  /^\/(opengraph-image|twitter-image)(\/|$)/,
  /^\/robots\.txt$/,
]

/** Refresh when the access token has less than this long to live. */
const REFRESH_SKEW_SECONDS = 120

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  if (BACKEND_PREFIX.test(pathname)) {
    return NextResponse.rewrite(new URL(pathname + search, backendUrl()))
  }
  // With skipTrailingSlashRedirect on (for Django), keep our own URLs canonical.
  if (pathname.length > 1 && pathname.endsWith('/')) {
    // Collapse leading slashes/backslashes too: absoluteUrl over a path like
    // '//evil.com' would resolve protocol-relative and 308 off-origin.
    const canonical = '/' + pathname.replace(/\/+$/, '').replace(/^[/\\]+/, '')
    return NextResponse.redirect(absoluteUrl(request, canonical + search), 308)
  }
  if (PUBLIC_ROUTES.some((route) => route.test(pathname))) {
    return NextResponse.next()
  }

  // BFF calls are fetches, not navigations: they get problem+json, never a
  // redirect to the login page.
  const isBff = pathname === '/bff' || pathname.startsWith('/bff/')

  const access = request.cookies.get(ACCESS_COOKIE)?.value
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value
  if (!refresh) return isBff ? bffUnauthorized(request, false) : toLogin(request)
  if (access && secondsUntilExpiry(access) > REFRESH_SKEW_SECONDS) {
    return NextResponse.next()
  }

  const result = await refreshAccess(refresh)
  if (result.kind === 'unreachable') {
    // Don't sign people out over a blip; the page's own API call will decide.
    return NextResponse.next()
  }
  if (result.kind === 'rejected') {
    const res = isBff ? bffUnauthorized(request, true) : toLogin(request)
    if (!isBff) clearAuthCookies(res.cookies)
    return res
  }

  // Make the new token visible to this render as well as to later requests.
  const headers = new Headers(request.headers)
  headers.set('cookie', replaceCookie(request.headers.get('cookie'), ACCESS_COOKIE, result.access))
  const res = NextResponse.next({ request: { headers } })
  res.cookies.set(ACCESS_COOKIE, result.access, authCookieOptions())
  return res
}

type RefreshResult = { kind: 'ok'; access: string } | { kind: 'rejected' } | { kind: 'unreachable' }

async function refreshAccess(refresh: string): Promise<RefreshResult> {
  try {
    const res = await fetch(`${backendUrl()}/api/auth/refresh/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ refresh }),
      cache: 'no-store',
    })
    if (!res.ok) return { kind: 'rejected' }
    const data = (await res.json().catch(() => null)) as { access?: unknown } | null
    return typeof data?.access === 'string'
      ? { kind: 'ok', access: data.access }
      : { kind: 'rejected' }
  } catch {
    return { kind: 'unreachable' }
  }
}

/** 401 problem+json for BFF fetches with no usable session. */
function bffUnauthorized(request: NextRequest, clear: boolean): NextResponse {
  const body = problemBody('unauthenticated', {
    detail: 'Sign in to use the BFF API.',
    instance: request.nextUrl.pathname,
  })
  const res = NextResponse.json(body, {
    status: 401,
    headers: { 'content-type': 'application/problem+json' },
  })
  if (clear) clearAuthCookies(res.cookies)
  return res
}

/** Redirect to the login page, remembering where the user was headed. */
function toLogin(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  const target = pathname + search
  const query = target === '/dashboard' ? '' : `?next=${encodeURIComponent(target)}`
  return NextResponse.redirect(absoluteUrl(request, `/${query}`), 307)
}

/**
 * Next requires an absolute Location. Behind Cloud Foundry TLS terminates at
 * the router, so trust the forwarded scheme/host over what Node sees.
 */
function absoluteUrl(request: NextRequest, path: string): URL {
  const proto =
    request.headers.get('x-forwarded-proto')?.split(',')[0].trim() ||
    request.nextUrl.protocol.replace(':', '')
  const host =
    request.headers.get('x-forwarded-host')?.split(',')[0].trim() ||
    request.headers.get('host') ||
    request.nextUrl.host
  return new URL(path, `${proto}://${host}`)
}

function replaceCookie(header: string | null, name: string, value: string): string {
  const kept = (header ?? '')
    .split(';')
    .map((part) => part.trim())
    .filter((part) => part && !part.startsWith(`${name}=`))
  return [...kept, `${name}=${value}`].join('; ')
}

export const config = {
  matcher: [
    // App routes: everything except Next internals and static-looking files.
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Backend prefixes must match even with file extensions (/static/admin/css/base.css).
    '/(admin|api|mcp|docs|swagger|redoc|schema|static|media|health|sse|messages)/:path*',
    '/(admin|api|mcp|docs|swagger|redoc|schema|static|media|health|sse|messages)',
  ],
}

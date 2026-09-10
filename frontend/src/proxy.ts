import { backendUrl, isTransientNetworkError } from '@/lib/api/backend-url'
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  authCookieOptions,
  clearAuthCookies,
} from '@/lib/auth/cookies'
import { secondsUntilExpiry } from '@/lib/auth/jwt'
import { problemBody } from '@/lib/bff/core/problem'
import { LANG_COOKIE, type Lang } from '@/lib/i18n'
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

/** Mirrors the client-side toggle's cookie (see lib/i18n-client.tsx). */
const LANG_COOKIE_OPTIONS = { path: '/', maxAge: 31536000, sameSite: 'lax' } as const

/** First visit carries no language cookie: default it from Accept-Language. */
function detectLang(header: string | null): Lang {
  const first = (header ?? '').split(',')[0]?.trim().toLowerCase() ?? ''
  return first === 'de' || first.startsWith('de-') ? 'de' : 'en'
}

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

  // No rs-lang cookie yet (first visit): pick from Accept-Language so a
  // German browser gets a German first paint. The user's toggle wins from
  // then on — this runs only while the cookie is absent.
  const newLang = request.cookies.get(LANG_COOKIE)
    ? null
    : detectLang(request.headers.get('accept-language'))

  if (PUBLIC_ROUTES.some((route) => route.test(pathname))) {
    return nextWithLang(request, newLang)
  }

  // BFF calls are fetches, not navigations: they get problem+json, never a
  // redirect to the login page.
  const isBff = pathname === '/bff' || pathname.startsWith('/bff/')

  const access = request.cookies.get(ACCESS_COOKIE)?.value
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value
  if (!refresh) {
    // An access cookie without its refresh partner means a session that ran
    // out (refresh maxAge passed); no cookies at all is just a signed-out
    // visitor, who must not be told their session expired.
    return isBff
      ? bffUnauthorized(request, false)
      : withLang(toLogin(request, access ? 'expired' : undefined), newLang)
  }
  if (access && secondsUntilExpiry(access) > REFRESH_SKEW_SECONDS) {
    return nextWithLang(request, newLang)
  }

  const result = await refreshAccess(refresh)
  if (result.kind === 'unreachable') {
    // Don't sign people out over a blip; the page's own API call will decide.
    return nextWithLang(request, newLang)
  }
  if (result.kind === 'rejected') {
    const res = isBff
      ? bffUnauthorized(request, true)
      : withLang(toLogin(request, 'expired'), newLang)
    if (!isBff) clearAuthCookies(res.cookies)
    return res
  }

  // Make the new token visible to this render as well as to later requests.
  const headers = new Headers(request.headers)
  let cookieHeader = replaceCookie(request.headers.get('cookie'), ACCESS_COOKIE, result.access)
  if (newLang) cookieHeader = replaceCookie(cookieHeader, LANG_COOKIE, newLang)
  headers.set('cookie', cookieHeader)
  const res = withLang(NextResponse.next({ request: { headers } }), newLang)
  res.cookies.set(ACCESS_COOKIE, result.access, authCookieOptions())
  // With ROTATE_REFRESH_TOKENS the refresh we just spent is blacklisted and a
  // replacement comes back with the access token. Storing it is what keeps the
  // session alive past the first refresh.
  if (result.refresh) res.cookies.set(REFRESH_COOKIE, result.refresh, authCookieOptions())
  return res
}

type RefreshResult =
  | { kind: 'ok'; access: string; refresh?: string }
  | { kind: 'rejected' }
  | { kind: 'unreachable' }

async function refreshAccess(refresh: string): Promise<RefreshResult> {
  const doFetch = () =>
    fetch(`${backendUrl()}/api/auth/refresh/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ refresh }),
      cache: 'no-store',
    })

  let res: Response
  try {
    res = await doFetch()
  } catch (error) {
    if (isTransientNetworkError(error)) {
      try {
        await new Promise((resolve) => setTimeout(resolve, 150))
        res = await doFetch()
      } catch {
        return { kind: 'unreachable' }
      }
    } else {
      return { kind: 'unreachable' }
    }
  }

  // 'rejected' signs the user out with "your session expired", so only a
  // verdict on the token counts. A 5xx is Django ailing, not the session
  // ending — treat it like a network failure and let the page's own API
  // call decide (a truly dead token still 401s there and signs out).
  if (res.status >= 500) return { kind: 'unreachable' }
  if (!res.ok) return { kind: 'rejected' }
  const data = (await res.json().catch(() => null)) as {
    access?: unknown
    refresh?: unknown
  } | null
  if (typeof data?.access !== 'string') return { kind: 'rejected' }
  // `refresh` is only present when the backend rotates; absent is not an error.
  return typeof data.refresh === 'string'
    ? { kind: 'ok', access: data.access, refresh: data.refresh }
    : { kind: 'ok', access: data.access }
}

/** Persist a freshly detected language on the response, if any. */
function withLang(res: NextResponse, lang: Lang | null): NextResponse {
  if (lang) res.cookies.set(LANG_COOKIE, lang, LANG_COOKIE_OPTIONS)
  return res
}

/**
 * NextResponse.next() that also makes a freshly detected language visible to
 * this very render (via the forwarded cookie header) and to later requests.
 */
function nextWithLang(request: NextRequest, lang: Lang | null): NextResponse {
  if (!lang) return NextResponse.next()
  const headers = new Headers(request.headers)
  headers.set('cookie', replaceCookie(request.headers.get('cookie'), LANG_COOKIE, lang))
  return withLang(NextResponse.next({ request: { headers } }), lang)
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

/**
 * Redirect to the login page, remembering where the user was headed and —
 * when the session demonstrably ended, rather than never existing — why.
 */
function toLogin(request: NextRequest, reason?: 'expired') {
  const { pathname, search } = request.nextUrl
  const target = pathname + search
  const query = new URLSearchParams()
  if (reason) query.set('reason', reason)
  if (target !== '/dashboard') query.set('next', target)
  const qs = query.toString()
  return NextResponse.redirect(absoluteUrl(request, qs ? `/?${qs}` : '/'), 307)
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

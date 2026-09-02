import { clearAuthCookies } from '@/lib/auth/cookies'
import { safeNext } from '@/lib/auth/safe-next'
import { isSameOrigin } from '@/lib/auth/same-origin'
import { NextResponse, type NextRequest } from 'next/server'

// Django has no logout endpoint (no token blacklist), so signing out is
// purely dropping the cookies. GET exists so server code can `redirect()`
// here when Django rejects a token mid-session (?reason=expired); the
// relative Location keeps the scheme/host the browser already uses.

/** The login page renders copy only for these; anything else is dropped. */
const REASONS = ['expired', 'signed-out']

function signOut(request: NextRequest) {
  // Forward reason + next so the login page can explain the landing and put
  // the user back where they were. `next` goes through safeNext — the same
  // validator the login route trusts — and is omitted when it folds to the
  // default landing (which is also how off-origin values drop out).
  const params = request.nextUrl.searchParams
  const reason = params.get('reason')
  const next = safeNext(params.get('next'))
  const query = new URLSearchParams()
  if (reason && REASONS.includes(reason)) query.set('reason', reason)
  if (next !== '/dashboard') query.set('next', next)
  const qs = query.toString()
  const res = new NextResponse(null, {
    status: 303,
    headers: { Location: qs ? `/?${qs}` : '/' },
  })
  clearAuthCookies(res.cookies)
  return res
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: 'Cross-site logout blocked.' }, { status: 403 })
  }
  return signOut(request)
}

export async function GET(request: NextRequest) {
  // A provably cross-site navigation must not drop the session (forced-logout
  // CSRF) — bounce home without touching the cookies. Same-origin flows, our
  // own server redirects, and address-bar entries ('none') all pass. A stale
  // session bounced this way still resolves: /dashboard's refresh fails and
  // the proxy clears the cookies on that hop.
  if (request.headers.get('sec-fetch-site') === 'cross-site') {
    return new NextResponse(null, { status: 303, headers: { Location: '/' } })
  }
  return signOut(request)
}

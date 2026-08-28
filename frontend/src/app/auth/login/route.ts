import { backendUrl } from '@/lib/api/backend-url'
import { apiErrorMessage } from '@/lib/api/server'
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  USER_COOKIE,
  authCookieOptions,
  encodeUserCookie,
  toCookieUser,
  type BackendUser,
} from '@/lib/auth/cookies'
import { safeNext } from '@/lib/auth/safe-next'
import { isSameOrigin } from '@/lib/auth/same-origin'
import { NextResponse, type NextRequest } from 'next/server'

// Exchanges credentials for Django's JWT pair and stores it in httpOnly
// cookies. Lives under /auth (not /api) because Cloud Foundry routes /api to
// Django before this app ever sees the request.

const GENERIC_ERROR = 'Those credentials did not match. Please try again.'

interface LoginBody {
  identifier?: string
  password?: string
  next?: string
}

interface DjangoLoginResponse {
  access: string
  refresh: string
  user?: BackendUser
  user_id?: number
  username?: string
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: 'Cross-site login blocked.' }, { status: 403 })
  }

  let body: LoginBody
  try {
    body = (await request.json()) as LoginBody
  } catch {
    return NextResponse.json({ error: 'Invalid request.' }, { status: 400 })
  }
  const identifier = body.identifier?.trim()
  const password = body.password
  if (!identifier || !password) {
    return NextResponse.json(
      { error: 'Enter your email or username and password.' },
      { status: 400 },
    )
  }

  let upstream: Response
  try {
    upstream = await fetch(`${backendUrl()}/api/auth/login/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      // Django resolves username first, then email (case-insensitive).
      body: JSON.stringify({ username_or_email: identifier, password }),
      cache: 'no-store',
    })
  } catch {
    return NextResponse.json(
      { error: 'The backend is unreachable. Try again shortly.' },
      { status: 502 },
    )
  }

  const data = (await upstream.json().catch(() => null)) as DjangoLoginResponse | null
  if (upstream.status === 401 || upstream.status === 403) {
    return NextResponse.json(
      { error: apiErrorMessage(data, GENERIC_ERROR) },
      { status: upstream.status },
    )
  }
  if (!upstream.ok || !data?.access || !data?.refresh) {
    // Anything else is a backend/config problem (e.g. ALLOWED_HOSTS rejecting
    // BACKEND_INTERNAL_URL's host) — don't disguise it as a bad password.
    return NextResponse.json(
      { error: `The backend could not process the sign-in (HTTP ${upstream.status}).` },
      { status: 502 },
    )
  }

  const user: BackendUser = data.user ?? {
    id: data.user_id ?? 0,
    username: data.username ?? identifier,
    email: '',
    first_name: '',
    last_name: '',
    full_name: '',
    is_superuser: false,
    is_staff: false,
  }

  const res = NextResponse.json({ ok: true, redirect: safeNext(body.next) })
  const options = authCookieOptions()
  res.cookies.set(ACCESS_COOKIE, data.access, options)
  res.cookies.set(REFRESH_COOKIE, data.refresh, options)
  res.cookies.set(USER_COOKIE, encodeUserCookie(toCookieUser(user)), options)
  return res
}


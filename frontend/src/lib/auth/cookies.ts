// Cookie names and options for the Django JWT session.
//
// Pure module — no `next/headers` import — so `src/proxy.ts`, route handlers,
// and server components can all share it. Django is the only verifier of the
// tokens; the frontend never checks signatures, it only decodes `exp`.

export const ACCESS_COOKIE = 'sri_access'
export const REFRESH_COOKIE = 'sri_refresh'
/** Display-only snapshot of the signed-in user, set at login. Unsigned:
 *  anything authorization-relevant must come from Django, not this cookie. */
export const USER_COOKIE = 'sri_user'
export const AUTH_COOKIES = [ACCESS_COOKIE, REFRESH_COOKIE, USER_COOKIE] as const

export interface CookieUser {
  id: number
  username: string
  email: string
  name: string
  isStaff: boolean
}

/** What the app chrome knows about the signed-in user. Safe to import from client components. */
export interface SessionUser extends CookieUser {
  image?: string
}

/** The `user` object Django returns from `/api/auth/login/` and `/api/auth/me/`. */
export interface BackendUser {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  is_superuser: boolean
  is_staff: boolean
}

export interface AuthCookieOptions {
  httpOnly: boolean
  sameSite: 'lax'
  path: string
  secure: boolean
  maxAge: number
}

export function authCookieOptions(): AuthCookieOptions {
  return {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    // Local `next start` on plain http needs COOKIE_SECURE=false.
    secure: process.env.NODE_ENV === 'production' && process.env.COOKIE_SECURE !== 'false',
    // Matches the SimpleJWT refresh lifetime (1 day). Freshness of the access
    // token is decided from its `exp` claim, not from the cookie lifetime.
    maxAge: 60 * 60 * 24,
  }
}

/** The subset of `ResponseCookies` / the `cookies()` store we rely on. */
export interface CookieWriter {
  set(name: string, value: string, options: AuthCookieOptions): unknown
}

export function clearAuthCookies(store: CookieWriter) {
  const expired = { ...authCookieOptions(), maxAge: 0 }
  for (const name of AUTH_COOKIES) store.set(name, '', expired)
}

export function toCookieUser(user: BackendUser): CookieUser {
  return {
    id: user.id,
    username: user.username,
    email: user.email ?? '',
    name: user.full_name?.trim() || user.username,
    isStaff: Boolean(user.is_staff || user.is_superuser),
  }
}

export function encodeUserCookie(user: CookieUser): string {
  return Buffer.from(JSON.stringify(user), 'utf8').toString('base64url')
}

export function decodeUserCookie(value: string | undefined): CookieUser | null {
  if (!value) return null
  try {
    const parsed: unknown = JSON.parse(Buffer.from(value, 'base64url').toString('utf8'))
    if (!parsed || typeof parsed !== 'object') return null
    const u = parsed as Partial<CookieUser>
    if (typeof u.username !== 'string' || typeof u.name !== 'string') return null
    return {
      id: typeof u.id === 'number' ? u.id : 0,
      username: u.username,
      email: typeof u.email === 'string' ? u.email : '',
      name: u.name,
      isStaff: Boolean(u.isStaff),
    }
  } catch {
    return null
  }
}

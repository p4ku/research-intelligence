import 'server-only'

import { ApiError, apiJson } from '@/lib/api/server'
import { cookies } from 'next/headers'
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  USER_COOKIE,
  decodeUserCookie,
  toCookieUser,
  type BackendUser,
  type CookieUser,
  type SessionUser,
} from './cookies'

export type { SessionUser }

/** `GET /api/auth/me/` — the login `user` object plus `workspaces_count`. */
export interface UserProfile extends BackendUser {
  workspaces_count: number | null
}

/** True when a refresh token is present — the proxy's gate condition. */
export async function hasSessionCookies(): Promise<boolean> {
  return Boolean((await cookies()).get(REFRESH_COOKIE)?.value)
}

/**
 * The signed-in user for chrome (name, email, initial). Read from the
 * display cookie set at login; falls back to one `/api/auth/me/` call if only
 * the access cookie exists (e.g. after a cookie-schema change mid-session).
 */
export async function getSessionUser(): Promise<SessionUser | null> {
  const store = await cookies()
  const cached = decodeUserCookie(store.get(USER_COOKIE)?.value)
  if (cached) return fromCookieUser(cached)
  if (!store.get(ACCESS_COOKIE)?.value) return null
  const profile = await getProfile()
  return profile ? fromCookieUser(toCookieUser(profile)) : null
}

/** Live profile from Django; null when the session is rejected. */
export async function getProfile(): Promise<UserProfile | null> {
  try {
    return await apiJson<UserProfile>('/api/auth/me/', { onUnauthorized: 'throw' })
  } catch (error) {
    if (error instanceof ApiError) return null
    throw error
  }
}

function fromCookieUser(u: CookieUser): SessionUser {
  return { id: u.id, username: u.username, name: u.name, email: u.email, isStaff: u.isStaff }
}

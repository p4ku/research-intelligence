/**
 * Stars service — the seam every star consumer goes through.
 *
 * Sources:
 * - `stub` (default): the per-browser cookie store (./cookie.ts). Reading
 *   works anywhere on the server; writing only in a route handler, where
 *   `cookies()` is writable — the PUT route is the one caller.
 * - `django`: the requested `/api/stars/` endpoint (validated pass-through).
 *
 * Server-only; always returns the contract shape (./schema.ts).
 */
import 'server-only'

import { authCookieOptions } from '@/lib/auth/cookies'
import { cookies } from 'next/headers'
import { django } from '../core/http'
import { sourceOf } from '../core/source'
import { decodeStarsCookie, encodeStarsCookie, STARS_COOKIE } from './cookie'
import { applyStar, stars as starsSchema, type Stars, type StarUpdate } from './schema'

const YEAR = 60 * 60 * 24 * 365

export const stars = {
  /** Everything the user has starred. */
  async get(): Promise<Stars> {
    if (sourceOf('stars') === 'django') return django('/api/stars/', starsSchema)
    return decodeStarsCookie((await cookies()).get(STARS_COOKIE)?.value)
  },

  /** Star or unstar one record; returns the full set afterwards. */
  async set(update: StarUpdate): Promise<Stars> {
    if (sourceOf('stars') === 'django') {
      return django('/api/stars/', starsSchema, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(update),
      })
    }
    const store = await cookies()
    const next = applyStar(decodeStarsCookie(store.get(STARS_COOKIE)?.value), update)
    // Same hardening as the session cookies (httpOnly, lax, Secure off plain
    // http), but it outlives a session: stars are not a credential.
    store.set(STARS_COOKIE, encodeStarsCookie(next), { ...authCookieOptions(), maxAge: YEAR })
    // The cookie is capped; report what was actually kept.
    return decodeStarsCookie(encodeStarsCookie(next))
  },
}

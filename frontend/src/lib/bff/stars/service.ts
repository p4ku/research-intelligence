/**
 * Stars service — the seam every star consumer goes through.
 *
 * Source: `django`, the `/api/stars/` endpoint (per user, idempotent), as a
 * validated pass-through. Server-only; always returns the contract shape
 * (./schema.ts).
 */
import 'server-only'

import { django } from '../core/http'
import { stars as starsSchema, type Stars, type StarUpdate } from './schema'

export const stars = {
  /** Everything the user has starred. */
  async get(): Promise<Stars> {
    return django('/api/stars/', starsSchema)
  },

  /** Star or unstar one record; returns the full set afterwards. */
  async set(update: StarUpdate): Promise<Stars> {
    return django('/api/stars/', starsSchema, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(update),
    })
  },
}

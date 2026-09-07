/**
 * The stub store's cookie codec. Until Django persists stars, the `stub`
 * source keeps them in one httpOnly cookie per browser — so they survive
 * reloads and deploys without the BFF inventing shared server state.
 * Pure (no `next/headers`), so the service, the route and the tests share it.
 *
 * A cookie holds ~4 KB. Each UUID is stored as its 16 bytes in base64url
 * (22 chars), ids joined by `.` and the two lists by `~` — both characters
 * survive cookie serialisation unencoded. The lists are capped, newest kept,
 * so the value can never outgrow the limit; the cap is a stub limitation,
 * not a product rule (the README says so).
 */
import { STARS_COOKIE } from '@/lib/auth/cookies'
import * as z from 'zod'
import { emptyStars, type Stars } from './schema'

export { STARS_COOKIE }
export const STARS_CAP = { papers: 80, briefings: 30 } as const

const ID_SEP = '.'
const LIST_SEP = '~'
// What the contract promises: a crafted cookie must not make GET /bff/stars
// return ids outside the `Stars` schema.
const uuid = z.uuid()

function pack(id: string): string {
  return Buffer.from(id.replace(/-/g, ''), 'hex').toString('base64url')
}

function unpack(packed: string): string | null {
  const bytes = Buffer.from(packed, 'base64url')
  if (bytes.length !== 16) return null
  const hex = bytes.toString('hex')
  const id = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  return uuid.safeParse(id).success ? id : null
}

/** Newest-last lists trimmed to the cap from the front (oldest dropped). */
export function capStars(value: Stars): Stars {
  return {
    papers: value.papers.slice(-STARS_CAP.papers),
    briefings: value.briefings.slice(-STARS_CAP.briefings),
  }
}

export function encodeStarsCookie(value: Stars): string {
  const capped = capStars(value)
  return [capped.papers, capped.briefings].map((ids) => ids.map(pack).join(ID_SEP)).join(LIST_SEP)
}

/** A missing or malformed cookie is simply "nothing starred". */
export function decodeStarsCookie(raw: string | undefined): Stars {
  if (!raw) return emptyStars
  const [papers = '', briefings = ''] = raw.split(LIST_SEP)
  const ids = (list: string): string[] =>
    list === '' ? [] : list.split(ID_SEP).flatMap((x) => unpack(x) ?? [])
  return capStars({ papers: ids(papers), briefings: ids(briefings) })
}

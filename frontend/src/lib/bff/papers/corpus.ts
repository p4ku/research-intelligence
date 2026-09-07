/**
 * The user's corpus, held for a short while across requests.
 *
 * `papers.listEverywhere()` is React-cached per request only, and under the
 * default `composed` source it re-derives every paper from Django each time
 * — fine for a page view, wrong for a keystroke or for a console that wants
 * the corpus a moment after it has painted. This keeps one corpus per
 * signed-in user for 45 s, keyed on a hash of the access token (the
 * credential Django verifies — never the unsigned display cookie), so one
 * user's cache can never answer another's request. Home's search and the
 * Ask picker read it; the pages keep their per-request freshness.
 *
 * Server-only.
 */
import 'server-only'

import { ACCESS_COOKIE } from '@/lib/auth/cookies'
import { cookies } from 'next/headers'
import { createHash } from 'node:crypto'
import { sourceOf } from '../core/source'
import { TtlCache } from '../core/ttl-cache'
import { papers, type CorpusPapers } from './service'

export const CORPUS_TTL_MS = 45_000
const CORPUS_MAX_USERS = 32

const corpusCache = new TtlCache<CorpusPapers>({
  ttlMs: CORPUS_TTL_MS,
  maxEntries: CORPUS_MAX_USERS,
})

/** The stub corpus is the same for everyone and needs no session. */
export async function corpusCacheKey(): Promise<string | null> {
  if (sourceOf('papers') === 'stub') return 'stub'
  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) return null
  return createHash('sha256').update(token).digest('base64url')
}

/** The user's corpus: cached for a short while; uncached without a session (Django answers 401). */
export async function recentCorpus(): Promise<CorpusPapers> {
  const key = await corpusCacheKey()
  return key ? corpusCache.get(key, papers.listEverywhere) : papers.listEverywhere()
}

/** Forget every cached corpus — a run just started, so every member's corpus is about to change. */
export function invalidateRecentCorpus(): void {
  corpusCache.clear()
}

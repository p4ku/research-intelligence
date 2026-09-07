/**
 * The corpus the typeahead searches, held for a short while across requests.
 *
 * `papers.listEverywhere()` is React-cached per request only, and under the
 * default `composed` source it re-derives the whole corpus from Django each
 * time — fine for a page view, not for a keystroke. This keeps one corpus
 * per signed-in user for 45 s, keyed on a hash of the access token (the
 * credential Django verifies — never the unsigned display cookie), so one
 * user's cache can never answer another's query. Only search reads it; the
 * pages keep their per-request freshness.
 *
 * Server-only.
 */
import 'server-only'

import { ACCESS_COOKIE } from '@/lib/auth/cookies'
import { cookies } from 'next/headers'
import { createHash } from 'node:crypto'
import { briefings } from '../briefings/service'
import { sourceOf } from '../core/source'
import { TtlCache } from '../core/ttl-cache'
import { papers } from '../papers/service'
import type { SearchCorpus } from './assemble'

const CORPUS_TTL_MS = 45_000
const CORPUS_MAX_USERS = 32

const corpusCache = new TtlCache<SearchCorpus>({
  ttlMs: CORPUS_TTL_MS,
  maxEntries: CORPUS_MAX_USERS,
})

async function loadCorpus(): Promise<SearchCorpus> {
  const { workspaces, papers: all } = await papers.listEverywhere()
  const latest = await Promise.all(
    workspaces.map(async (ws): Promise<[string, string | null]> => {
      const editions = await briefings.listAll(ws.id, 'en')
      return [ws.id, editions[0]?.date ?? null]
    }),
  )
  return { workspaces, papers: all, latestEdition: Object.fromEntries(latest) }
}

async function cacheKey(): Promise<string | null> {
  // The stub corpus is the same for everyone and needs no session.
  if (sourceOf('papers') === 'stub') return 'stub'
  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) return null
  return createHash('sha256').update(token).digest('base64url')
}

/** The user's corpus: cached for a short while; uncached without a session (Django answers 401). */
export async function searchCorpus(): Promise<SearchCorpus> {
  const key = await cacheKey()
  return key ? corpusCache.get(key, loadCorpus) : loadCorpus()
}

/** Forget every cached corpus — a run just started, so every member's corpus is about to change. */
export function invalidateSearchCorpus(): void {
  corpusCache.clear()
}

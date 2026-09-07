/**
 * The corpus the typeahead searches: the user's recent corpus (shared with
 * the Ask picker, see ../papers/corpus.ts) plus each domain's newest edition
 * date. The editions are one briefings fetch per domain, so the assembled
 * result is held for the same short while, under the same per-user key.
 *
 * Server-only.
 */
import 'server-only'

import { briefings } from '../briefings/service'
import { TtlCache } from '../core/ttl-cache'
import {
  CORPUS_TTL_MS,
  corpusCacheKey,
  invalidateRecentCorpus,
  recentCorpus,
} from '../papers/corpus'
import type { SearchCorpus } from './assemble'

const CORPUS_MAX_USERS = 32

const searchCache = new TtlCache<SearchCorpus>({
  ttlMs: CORPUS_TTL_MS,
  maxEntries: CORPUS_MAX_USERS,
})

async function loadCorpus(): Promise<SearchCorpus> {
  const { workspaces, papers: all } = await recentCorpus()
  const latest = await Promise.all(
    workspaces.map(async (ws): Promise<[string, string | null]> => {
      const editions = await briefings.listAll(ws.id, 'en')
      return [ws.id, editions[0]?.date ?? null]
    }),
  )
  return { workspaces, papers: all, latestEdition: Object.fromEntries(latest) }
}

/** The user's search corpus: cached for a short while; uncached without a session (Django answers 401). */
export async function searchCorpus(): Promise<SearchCorpus> {
  const key = await corpusCacheKey()
  return key ? searchCache.get(key, loadCorpus) : loadCorpus()
}

/** Forget every cached corpus, search's and the papers' — a run just started. */
export function invalidateSearchCorpus(): void {
  searchCache.clear()
  invalidateRecentCorpus()
}

/**
 * The user's corpus, held across requests.
 *
 * Every derived read in the app — scored papers, editions, scoring, search,
 * the Ask palette — funnels through three raw Django lists: workspaces,
 * papers, extractions. This holds them per signed-in user as two
 * snapshots — the small workspaces list every page reads, and the heavy
 * papers + extractions pair only the corpus pages read — so the ~1 MB
 * corpus is pulled and parsed once, not once per navigation, and a page
 * that never reads papers neither waits on them nor fails with them.
 *
 * Freshness comes from Django, not from a clock: the corpus only changes
 * when a pipeline run writes it, so the run ledger's fingerprint
 * (./version.ts) is the version, and a probe of the run list on every
 * request decides whether the lists are re-pulled. Pages that render the
 * run list anyway (Home, /runs, /briefing) pay nothing for the probe — it
 * shares their per-request `cache()`; the rest pay one small round trip in
 * place of the corpus. Confirming on every request is what lets the render
 * that first shows a run as completed also be the first with its papers —
 * the explicit invalidation below is only a shortcut, since a route
 * handler's module state need not be the pages'. A request that can live
 * with a few seconds of lag (the typeahead's keystrokes) says so through
 * `trustCorpusFor`. The policy itself lives in ./store.ts.
 *
 * Keyed on a hash of the access token — the credential Django verifies,
 * never the unsigned display cookie — so one user's snapshot can never
 * answer another's request. A refreshed token is a new key: one cold load
 * per user per hour, accepted. Server-only.
 */
import 'server-only'

import type { ExtractionDTO, PaperDTO, WorkspaceDTO } from '@/lib/api/types'
import { ACCESS_COOKIE } from '@/lib/auth/cookies'
import { cookies } from 'next/headers'
import { createHash } from 'node:crypto'
import { cache } from 'react'
import * as z from 'zod'
import { django } from '../core/http'
import { sourceOf } from '../core/source'
import { extractionDTO, paperDTO } from '../papers/upstream'
import { runs } from '../pipeline-runs/service'
import { workspaceDTO } from '../workspaces/upstream'
import { createSnapshotStore } from './store'
import { corpusVersion } from './version'

export interface CorpusSnapshot {
  /** Empty unless papers are `composed` — the other sources never read them. */
  papers: PaperDTO[]
  extractions: ExtractionDTO[]
}

/** The backstop for changes no run explains (an admin edit, a backfill). */
export const SNAPSHOT_TTL_MS = 10 * 60_000
/**
 * Live keys at once. Parsed DTOs run to a few MB per user; the cache is
 * least-recently-used, so a burst of users past this degrades to cold loads
 * for the least active rather than for everyone.
 */
const SNAPSHOT_MAX_USERS = 16

/** One run-ledger probe per request, shared by both stores and the pages. */
const probe = async () => corpusVersion(await runs.listEverywhere())

const workspacesStore = createSnapshotStore<WorkspaceDTO[]>({
  probe,
  load: () => django('/api/workspaces/', z.array(workspaceDTO)),
  ttlMs: SNAPSHOT_TTL_MS,
  maxEntries: SNAPSHOT_MAX_USERS,
})

const corpusStore = createSnapshotStore<CorpusSnapshot>({
  probe,
  load: async () => {
    if (sourceOf('papers') !== 'composed') return { papers: [], extractions: [] }
    const [papers, extractions] = await Promise.all([
      django('/api/papers/', z.array(paperDTO)),
      django('/api/extractions/', z.array(extractionDTO)),
    ])
    return { papers, extractions }
  },
  ttlMs: SNAPSHOT_TTL_MS,
  maxEntries: SNAPSHOT_MAX_USERS,
})

/** The per-user key; null without a session, when nothing may be cached. */
export async function corpusCacheKey(): Promise<string | null> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) return null
  return createHash('sha256').update(token).digest('base64url')
}

/** Per request: how long a confirmed version may be trusted without probing. */
const trust = cache(() => ({ ms: 0 }))

/**
 * Let this request serve a version confirmed within `ms` without probing —
 * for reads where a few seconds of lag are invisible, like a typing burst.
 * Call before the first corpus read of the request.
 */
export function trustCorpusFor(ms: number): void {
  trust().ms = ms
}

/** The user's workspaces, once per request. */
export const workspacesSnapshot = cache(
  async (): Promise<WorkspaceDTO[]> =>
    workspacesStore.get(await corpusCacheKey(), { trustMs: trust().ms }),
)

/** The user's papers and extractions, once per request. */
export const corpusSnapshot = cache(
  async (): Promise<CorpusSnapshot> =>
    corpusStore.get(await corpusCacheKey(), { trustMs: trust().ms }),
)

/** Forget every user's snapshot — a run just started, so every corpus is about to change. */
export function invalidateCorpusSnapshot(): void {
  workspacesStore.invalidate()
  corpusStore.invalidate()
}

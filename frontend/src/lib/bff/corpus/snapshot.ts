/**
 * The user's corpus, held across requests.
 *
 * Every derived read in the app — scored papers, editions, scoring, search,
 * the Ask palette — funnels through three raw Django lists: workspaces,
 * papers, extractions. This holds those three as one coherent snapshot per
 * signed-in user and serves it to every page, so the ~1 MB corpus is pulled
 * and parsed once, not once per navigation.
 *
 * Freshness comes from Django, not from a clock: the corpus only changes
 * when a pipeline run writes it, so the run ledger's fingerprint
 * (./version.ts) is the version, and a 1.5 KB probe of the run list decides
 * whether the heavy lists are re-pulled. Pages that render the run list
 * anyway (Home, /runs, /briefing) pay nothing for the probe — it shares
 * their per-request `cache()`. The policy itself lives in ./store.ts.
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
  workspaces: WorkspaceDTO[]
  /** Empty unless papers are `composed` — the other sources never read them. */
  papers: PaperDTO[]
  extractions: ExtractionDTO[]
}

/** A confirmed version is trusted this long before the run list is probed again. */
export const PROBE_COOLDOWN_MS = 10_000
/** The backstop for changes no run explains (an admin edit, a backfill). */
export const SNAPSHOT_TTL_MS = 10 * 60_000
/** Parsed DTOs run to a few MB per user; eight users fit a 512 MB instance comfortably. */
const SNAPSHOT_MAX_USERS = 8

async function loadCorpus(): Promise<CorpusSnapshot> {
  const composed = sourceOf('papers') === 'composed'
  const [workspaces, papers, extractions] = await Promise.all([
    django('/api/workspaces/', z.array(workspaceDTO)),
    composed ? django('/api/papers/', z.array(paperDTO)) : [],
    composed ? django('/api/extractions/', z.array(extractionDTO)) : [],
  ])
  return { workspaces, papers, extractions }
}

const store = createSnapshotStore<CorpusSnapshot>({
  probe: async () => corpusVersion(await runs.listEverywhere()),
  load: loadCorpus,
  cooldownMs: PROBE_COOLDOWN_MS,
  ttlMs: SNAPSHOT_TTL_MS,
  maxEntries: SNAPSHOT_MAX_USERS,
})

/** The per-user key; null without a session, when nothing may be cached. */
export async function corpusCacheKey(): Promise<string | null> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) return null
  return createHash('sha256').update(token).digest('base64url')
}

/** The user's corpus snapshot, once per request. */
export const corpusSnapshot = cache(
  async (): Promise<CorpusSnapshot> => store.get(await corpusCacheKey()),
)

/** Forget every user's snapshot — a run just started, so every corpus is about to change. */
export function invalidateCorpusSnapshot(): void {
  store.invalidate()
}

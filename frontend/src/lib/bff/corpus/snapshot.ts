/**
 * The user's corpus, held across requests.
 *
 * Every derived read in the app — scored papers, editions, scoring, search,
 * the Ask palette — funnels through three raw Django lists: workspaces,
 * papers, extractions. This holds them per signed-in user as two
 * snapshots — the small workspaces list every page reads, and the heavy
 * papers + extractions pair only the corpus pages read — so the corpus is
 * pulled and parsed once, not once per navigation, and a page that never
 * reads papers neither waits on them nor fails with them. Under `papers:
 * django` the papers + extractions pair gives way to a third snapshot, the
 * scored corpus: Django's scorecard per domain, already scored, held the
 * same way (./scored.ts walks it).
 *
 * The corpus is bounded twice. Per user, the papers list is walked
 * newest-first in pages and stops at `CORPUS_MAX_PAPERS`: an analyst with
 * more history than that sees the newest papers and a line saying so
 * (`truncated`), never a slower page or an outage. Extractions follow the
 * kept papers (./window.ts). What lies past the cap is read live where one
 * record is wanted — a paper's page, one edition — and is simply absent from
 * the composed lists (briefings, stars), which say nothing about it; the
 * cap is meant to sit above any real corpus. Across users, the cache holds at most
 * `CORPUS_CACHE_MAX_MB` of JSON as received — least recently used goes
 * first — on top of the key count.
 *
 * Freshness comes from Django, not from a clock: the corpus only changes
 * when a pipeline run writes it, so the run ledger's fingerprint
 * (./version.ts) is the version, and a probe of the run list decides whether
 * the lists are re-pulled. A request that reads the ledger itself — Home,
 * /runs, /briefing — always probes; the probe is that fetch, shared through
 * the per-request `cache()`, and the render that first shows a run completed
 * is then the first with its papers. Every other request trusts a version
 * confirmed within `CORPUS_PROBE_COOLDOWN_MS`, so a navigation burst is one
 * ledger fetch, and may raise that for itself through `trustCorpusFor` (the
 * typeahead's keystrokes). The explicit invalidation below is only a
 * shortcut, since a route handler's module state need not be the pages'.
 * The policy itself lives in ./store.ts.
 *
 * Keyed on a hash of the access token — the credential Django verifies,
 * never the unsigned display cookie — so one user's snapshot can never
 * answer another's request. A refreshed token is a new key: one cold load
 * per user per hour, accepted. Server-only.
 */
import 'server-only'

import type { ExtractionDTO, PaperDTO, WorkspaceDTO } from '@/lib/api/types'
import { ACCESS_COOKIE } from '@/lib/auth/cookies'
import type { ScoredPaper } from '@/lib/papers/types'
import { cookies } from 'next/headers'
import { createHash } from 'node:crypto'
import { cache } from 'react'
import * as z from 'zod'
import { drain } from '../core/drain'
import { intEnv } from '../core/env'
import { django, djangoPage } from '../core/http'
import { sourceOf } from '../core/source'
import { scoredPaper } from '../papers/schema'
import { extractionDTO, paperDTO } from '../papers/upstream'
import { runs } from '../pipeline-runs/service'
import { workspaceDTO } from '../workspaces/upstream'
import { isHiddenWorkspace } from '../workspaces/visible'
import { ledgerRequested } from './ledger-flag'
import { drainScored, type ScoredDrained } from './scored'
import { createSnapshotStore, effectiveTrust } from './store'
import { corpusVersion } from './version'
import { extractionCutoff, truncation } from './window'

export interface CorpusSnapshot {
  /** Empty unless papers are `composed` — the other sources never read them. */
  papers: PaperDTO[]
  extractions: ExtractionDTO[]
  /** Set when the cap dropped older papers: the newest `kept` of `total` are here. */
  truncated?: { kept: number; total: number }
  /** JSON bytes as received — what the cache budget weighs. */
  bytes: number
}

/** The backstop for changes no run explains (an admin edit, a backfill). */
export const SNAPSHOT_TTL_MS = 10 * 60_000
/**
 * Live keys at once. The byte budget below is the real bound; this keeps a
 * burst of users degrading to cold loads for the least active rather than
 * for everyone.
 */
const SNAPSHOT_MAX_USERS = 16
/** Django's `max_page_size` (backend/api/pagination.py). */
export const CORPUS_PAGE_SIZE = 500
/** What the scorecard endpoint clamps `page_size` to (build_workspace_scorecard_data). */
export const SCORECARD_PAGE_SIZE = 200
/** The newest papers a user's snapshot keeps. Documented in .env.example. */
export const CORPUS_MAX_PAPERS = intEnv('CORPUS_MAX_PAPERS', 2000, { min: 1 })
/** Retained JSON across users; V8 holds roughly twice this once parsed. */
export const CORPUS_CACHE_MAX_MB = intEnv('CORPUS_CACHE_MAX_MB', 128, { min: 1 })
/** How long a confirmed version is trusted on a request that did not read the ledger. */
export const CORPUS_PROBE_COOLDOWN_MS = intEnv('CORPUS_PROBE_COOLDOWN_MS', 5_000, { min: 0 })
/**
 * Pages of extractions read at most. Kept papers' extractions run ~3 per
 * paper; the walk also reads past newer extractions of dropped papers (a
 * reprocess run rewrites whole workspaces), so this bounds pages, not rows.
 */
const EXTRACTION_PAGES_CEILING = Math.ceil((CORPUS_MAX_PAPERS * 8) / CORPUS_PAGE_SIZE) + 8

/** One run-ledger probe per request, shared by both stores and the pages. */
const probe = async () => corpusVersion(await runs.listEverywhere())

const workspacesStore = createSnapshotStore<WorkspaceDTO[]>({
  probe,
  load: () => django('/api/workspaces/', z.array(workspaceDTO)),
  ttlMs: SNAPSHOT_TTL_MS,
  maxEntries: SNAPSHOT_MAX_USERS,
})

async function loadCorpus(): Promise<CorpusSnapshot> {
  if (sourceOf('papers') !== 'composed') return { papers: [], extractions: [], bytes: 0 }
  const papers = await drain((page, size) => djangoPage('/api/papers/', paperDTO, page, size), {
    pageSize: CORPUS_PAGE_SIZE,
    maxItems: CORPUS_MAX_PAPERS,
    id: (p) => p.id,
  })
  const truncated = truncation(papers.items.length, papers.total, CORPUS_MAX_PAPERS)
  if (truncated) {
    console.warn(
      '[bff] corpus capped: kept newest %d of %d papers (CORPUS_MAX_PAPERS=%d)',
      truncated.kept,
      truncated.total,
      CORPUS_MAX_PAPERS,
    )
  }
  const cutoff = extractionCutoff(papers.items)
  if (cutoff === null) return { papers: [], extractions: [], truncated, bytes: papers.bytes }
  // Newest-first down to the oldest kept paper reaches every extraction of a
  // kept paper; only those are kept, so a dropped paper's rows count toward
  // nothing but the pages read.
  const kept = new Set(papers.items.map((p) => p.id))
  const extractions = await drain(
    (page, size) => djangoPage('/api/extractions/', extractionDTO, page, size),
    {
      pageSize: CORPUS_PAGE_SIZE,
      maxItems: Number.POSITIVE_INFINITY,
      id: (e) => e.id,
      accept: (e) => kept.has(e.paper),
      until: (e) => Date.parse(e.created_at) < cutoff,
      maxPages: EXTRACTION_PAGES_CEILING,
    },
  )
  if (extractions.cutShort) {
    console.warn(
      '[bff] extractions walk stopped after %d pages; some dimensions may be missing',
      extractions.pages,
    )
  }
  return {
    papers: papers.items,
    extractions: extractions.items,
    truncated,
    bytes: papers.bytes + extractions.bytes,
  }
}

/** Whether a paper is one the snapshot holds — false past the cap. */
export async function corpusHolds(paperId: string): Promise<boolean> {
  const { papers, truncated } = await corpusSnapshot()
  if (!truncated) return true
  return papers.some((p) => p.id === paperId)
}

const corpusStore = createSnapshotStore<CorpusSnapshot>({
  probe,
  load: loadCorpus,
  ttlMs: SNAPSHOT_TTL_MS,
  maxEntries: SNAPSHOT_MAX_USERS,
  maxBytes: CORPUS_CACHE_MAX_MB * 1_048_576,
  sizeOf: (snapshot) => snapshot.bytes,
})

export type ScoredCorpus = ScoredDrained<ScoredPaper>

/**
 * The scored papers of every domain the user belongs to, as Django's
 * scorecard serves them. Nothing is derived from these rows — they arrive
 * scored — so what this adds is the holding: one drain per domain per
 * corpus version, not one per page view. Calibration domains are left out
 * here as everywhere (../workspaces/visible.ts), so their papers never cost
 * a page read or a place under the cap. The bytes weighed are the pages as
 * received; Django still sends each page's list twice (`papers` and
 * `results`, docs/scorecard-backlog.md item 7), and only `results` is kept,
 * so the budget errs on the safe side until that is fixed.
 */
async function loadScored(): Promise<ScoredCorpus> {
  if (sourceOf('papers') === 'stub') return { byWorkspace: new Map(), bytes: 0 }
  const memberships = (await workspacesSnapshot()).filter((ws) => !isHiddenWorkspace(ws.name))
  const corpus = await drainScored(
    memberships.map((ws) => ws.id),
    (workspaceId, page, size) =>
      djangoPage(`/api/workspaces/${workspaceId}/scorecard/`, scoredPaper, page, size),
    { pageSize: SCORECARD_PAGE_SIZE, cap: CORPUS_MAX_PAPERS },
  )
  if (corpus.truncated) {
    console.warn(
      '[bff] scored corpus capped: kept newest %d of %d papers (CORPUS_MAX_PAPERS=%d)',
      corpus.truncated.kept,
      corpus.truncated.total,
      CORPUS_MAX_PAPERS,
    )
  }
  return corpus
}

const scoredStore = createSnapshotStore<ScoredCorpus>({
  probe,
  load: loadScored,
  ttlMs: SNAPSHOT_TTL_MS,
  maxEntries: SNAPSHOT_MAX_USERS,
  maxBytes: CORPUS_CACHE_MAX_MB * 1_048_576,
  sizeOf: (corpus) => corpus.bytes,
})

/** The per-user key; null without a session, when nothing may be cached. */
export async function corpusCacheKey(): Promise<string | null> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) return null
  return createHash('sha256').update(token).digest('base64url')
}

/** Per request: how long this request asked to trust a confirmed version. */
const trust = cache(() => ({ ms: 0 }))

/**
 * Let this request serve a version confirmed within `ms` without probing —
 * for reads where a few seconds of lag are invisible, like a typing burst.
 * Only ever raises the process-wide cooldown. Call before the first corpus
 * read of the request.
 */
export function trustCorpusFor(ms: number): void {
  trust().ms = Math.max(trust().ms, ms)
}

/**
 * Read at the moment a store is consulted. The pages that render the ledger
 * (Home, /runs, /briefing) call `runs.listEverywhere()` before their first
 * corpus read reaches this — `composeAll` lists runs first, and both reads
 * below await `cookies()` before looking — so on those pages the flag is set
 * in time. Keep that order when adding a page that shows both.
 */
function trustMs(): number {
  return effectiveTrust({
    requested: trust().ms,
    cooldownMs: CORPUS_PROBE_COOLDOWN_MS,
    ledgerRequested: ledgerRequested().yes,
  })
}

/** The user's workspaces, once per request. */
export const workspacesSnapshot = cache(
  async (): Promise<WorkspaceDTO[]> =>
    workspacesStore.get(await corpusCacheKey(), { trustMs: trustMs() }),
)

/** The user's papers and extractions, once per request. */
export const corpusSnapshot = cache(
  async (): Promise<CorpusSnapshot> =>
    corpusStore.get(await corpusCacheKey(), { trustMs: trustMs() }),
)

/** The user's scored papers per domain, once per request. */
export const scoredCorpus = cache(
  async (): Promise<ScoredCorpus> =>
    scoredStore.get(await corpusCacheKey(), { trustMs: trustMs() }),
)

/** Forget every user's snapshot — a run just started, so every corpus is about to change. */
export function invalidateCorpusSnapshot(): void {
  workspacesStore.invalidate()
  corpusStore.invalidate()
  scoredStore.invalidate()
}

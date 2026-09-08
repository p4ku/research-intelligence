import 'server-only'

import type { Edition } from '@/lib/bff/briefings/schema'
import { briefings } from '@/lib/bff/briefings/service'
import { papers } from '@/lib/bff/papers/service'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import type { Lang } from '@/lib/i18n'
import { cache } from 'react'
import { inFlightIds, selectRecent, type RecentBriefing } from './recent'

/**
 * Per-request accessors for Home's streamed section. `cache()` de-duplicates
 * within a request (the ledger reads the run list once and the current run
 * again for its status column). "Current" is the newest completed run in
 * any of the user's domains.
 */

/**
 * Every run the user can see, newest first by the run clock — the order
 * `runs.listEverywhere` keeps (lib/bff/pipeline-runs/clock.ts). Not re-sorted
 * here: the live refresh polls a page of the same list through
 * /bff/pipeline-runs and compares in-flight sets, so both windows must be
 * cut from one order or they can differ forever.
 */
export const allRuns = cache(async (): Promise<PipelineRun[]> => runsService.listEverywhere())

export const currentRun = cache(
  async () => (await allRuns()).find((run) => run.status === 'completed') ?? null,
)

/**
 * Recent Briefings (see recent.ts for the rule). The editions are the same
 * list the archive reads — one fetch per domain, in parallel, cached — so
 * the two screens agree by construction. A completed run with no edition
 * here briefed nothing, or is in a domain whose corpus could not be read.
 */
export const recentBriefings = cache(async (lang: Lang): Promise<RecentBriefing[]> => {
  // `allRuns` first: the corpus probe reads the run ledger this request already asked for.
  const [all, editions, capped] = await Promise.all([
    allRuns(),
    briefings.listEverywhere(lang),
    papers.corpusTruncated(),
  ])
  const byRun = new Map<string, Edition>(editions.map((e) => [e.run_id, e]))
  return selectRecent(all, byRun, capped)
})

/**
 * The runs in flight, newest first, within the window the live refresh
 * polls — what disables Start New Briefing and what the poll compares its
 * page against. Not the ledger's rows: a run in flight is a row only while
 * it is newer than the fifth briefing, but it must be watched regardless.
 */
export const inFlightRuns = cache(async (): Promise<PipelineRun[]> => {
  const all = await allRuns()
  const ids = new Set(inFlightIds(all))
  return all.filter((run) => ids.has(run.id))
})

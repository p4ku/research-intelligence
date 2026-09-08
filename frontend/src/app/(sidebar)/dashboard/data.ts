import 'server-only'

import type { Edition } from '@/lib/bff/briefings/schema'
import { briefings } from '@/lib/bff/briefings/service'
import { papers } from '@/lib/bff/papers/service'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import type { Lang } from '@/lib/i18n'
import { cache } from 'react'
import { hasBriefing } from '../briefing/rows'

/**
 * Per-request accessors for Home's streamed section. `cache()` de-duplicates
 * within a request (the ledger reads the run list once and the current run
 * again for its status column). "Current" is the newest completed run in
 * any of the user's domains.
 */

/** At most this many rows in Recent Briefings, newest first. */
export const RECENT = 5

/** Every run the user can see, newest first (Django's order, re-asserted). */
export const allRuns = cache(async (): Promise<PipelineRun[]> => {
  const list = await runsService.listEverywhere()
  return list
    .slice()
    .sort((a, b) => (b.started_at ?? b.run_date).localeCompare(a.started_at ?? a.run_date))
})

export const currentRun = cache(
  async () => (await allRuns()).find((run) => run.status === 'completed') ?? null,
)

/**
 * The edition a completed run produced, or null when none was composed
 * for it (an older same-day rerun collapses into the newer one; a domain
 * whose corpus could not be read yields no editions at all).
 */
export const editionFor = cache(
  async (workspaceId: string, runId: string, lang: Lang): Promise<Edition | null> =>
    (await briefings.listAll(workspaceId, lang)).find((e) => e.run_id === runId) ?? null,
)

export interface RecentBriefing {
  run: PipelineRun
  /** The run's edition; null while it is still processing or after it failed. */
  edition: Edition | null
}

/**
 * Recent Briefings: the newest RECENT briefings across the user's domains,
 * newest first — the first page of the archive, with the runs still in
 * flight or just failed kept in their place, because a briefing that is
 * coming (or did not come) belongs beside the ones that did. A completed run
 * that briefed nothing is not a briefing, so it is not a row; the archive
 * applies the same rule, so the two screens list the same runs. The walk
 * stops at RECENT: editions are read per domain and cached, so it costs one
 * list per domain touched, not one per run.
 */
export const recentBriefings = cache(async (lang: Lang): Promise<RecentBriefing[]> => {
  const [all, capped] = await Promise.all([allRuns(), papers.corpusTruncated()])
  const rows: RecentBriefing[] = []
  for (const run of all) {
    if (rows.length === RECENT) break
    if (run.status !== 'completed') {
      rows.push({ run, edition: null })
      continue
    }
    const edition = await editionFor(run.workspace_id, run.id, lang)
    if (hasBriefing(run.total_papers_passed_screening, edition, capped)) rows.push({ run, edition })
  }
  return rows
})

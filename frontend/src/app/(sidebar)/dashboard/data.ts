import 'server-only'

import type { Edition } from '@/lib/bff/briefings/schema'
import { briefings } from '@/lib/bff/briefings/service'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import type { Lang } from '@/lib/i18n'
import { cache } from 'react'

/**
 * Per-request accessors for Home's streamed section. `cache()` de-duplicates
 * within a request (the ledger reads the run list once and the current run
 * again for its status column). "Current" is the newest completed run in
 * any of the user's domains.
 */

/** Exactly this many rows in Recent Briefings, newest first. */
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

export const recentRuns = cache(
  async (lang: Lang): Promise<{ run: PipelineRun; edition: Edition | null }[]> => {
    const recent = (await allRuns()).slice(0, RECENT)
    const editions = await Promise.all(
      recent.map((run) =>
        run.status === 'completed' ? editionFor(run.workspace_id, run.id, lang) : null,
      ),
    )
    return recent.map((run, i) => ({ run, edition: editions[i] }))
  },
)

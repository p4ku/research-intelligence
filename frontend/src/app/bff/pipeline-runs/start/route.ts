import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { parseBody } from '@/lib/bff/core/validate'
import { invalidateCorpusSnapshot } from '@/lib/bff/corpus/snapshot'
import { startRun } from '@/lib/bff/pipeline-runs/schema'
import { runs } from '@/lib/bff/pipeline-runs/service'

export const dynamic = 'force-dynamic'

/**
 * Home's "Start" (New briefing) and a failed row's Retry: one domain, one search
 * window. One run at a time across all analysts is the spec's rule and
 * Django does not enforce it, so it is checked here against the live list
 * — a stale Home (another analyst started a run since it rendered) gets a
 * 409 and re-reads itself rather than starting a second run. The window
 * between the check and Django's create remains; it is milliseconds, not
 * the lifetime of a stale tab.
 */
export const POST = bff('pipeline-runs', async (request) => {
  const input = await parseBody(startRun, request)
  const inFlight = (await runs.listEverywhere()).find(
    (run) => run.status === 'running' || run.status === 'pending',
  )
  if (inFlight) {
    throw problem('conflict', {
      detail: `A run for ${inFlight.workspace_name} is already in progress.`,
    })
  }
  const started = await runs.start(input)
  invalidateCorpusSnapshot()
  return Response.json(started, { status: 201 })
})

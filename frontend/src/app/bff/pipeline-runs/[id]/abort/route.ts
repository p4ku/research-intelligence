import { bff } from '@/lib/bff/core/handler'
import { invalidateCorpusSnapshot } from '@/lib/bff/corpus/snapshot'
import { runs } from '@/lib/bff/pipeline-runs/service'

export const dynamic = 'force-dynamic'

/**
 * Stop one run. The refusal shapes are the service's (409 once the run has
 * ended, 403 unless the caller is an admin or manager); the page re-reads the
 * list for the row's new status rather than trusting the envelope.
 */
export const POST = bff('pipeline-runs', async (_request, ctx) => {
  const { id } = await ctx.params
  const stopped = await runs.abort(id)
  // The stopped run gains a completed_at, so it is the newest by the run
  // clock — the key the corpus probe versions on changed, as after a start.
  invalidateCorpusSnapshot()
  return Response.json(stopped)
})

import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'
import { startRun } from '@/lib/bff/pipeline-runs/schema'
import { runs } from '@/lib/bff/pipeline-runs/service'

export const dynamic = 'force-dynamic'

/** Home's "Run pipeline" and a failed row's Retry: one domain, one search window. */
export const POST = bff('pipeline-runs', async (request) => {
  const input = await parseBody(startRun, request)
  const started = await runs.start(input)
  return Response.json(started, { status: 201 })
})

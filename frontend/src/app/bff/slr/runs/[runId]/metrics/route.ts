import { bff } from '@/lib/bff/core/handler'
import { slr } from '@/lib/bff/slr/service'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async (_req, ctx) => {
  const { runId } = await ctx.params
  const metrics = await slr.getMetrics(runId)
  return Response.json(metrics)
})

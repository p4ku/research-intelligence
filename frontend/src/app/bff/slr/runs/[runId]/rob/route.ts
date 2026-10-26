import { bff } from '@/lib/bff/core/handler'
import { slr } from '@/lib/bff/slr/service'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async (_req, ctx) => {
  const { runId } = await ctx.params
  const rob = await slr.getRiskOfBias(runId)
  return Response.json(rob)
})

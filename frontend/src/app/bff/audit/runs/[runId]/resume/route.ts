import { audit } from '@/lib/bff/audit/service'
import { bff } from '@/lib/bff/core/handler'

export const dynamic = 'force-dynamic'

export const POST = bff('audit', async (_request, ctx) => {
  const { runId } = await ctx.params
  const result = await audit.resumeRun(runId)
  return Response.json(result, { status: 200 })
})

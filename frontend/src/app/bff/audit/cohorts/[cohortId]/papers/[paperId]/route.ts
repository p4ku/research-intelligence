import { audit } from '@/lib/bff/audit/service'
import { bff } from '@/lib/bff/core/handler'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async (_request, ctx) => {
  const { cohortId, paperId } = await ctx.params
  const paper = await audit.getPaper(cohortId, paperId)
  return Response.json(paper)
})

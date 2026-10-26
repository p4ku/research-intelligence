import { submitAuditDecision } from '@/lib/bff/audit/schema'
import { audit } from '@/lib/bff/audit/service'
import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'

export const dynamic = 'force-dynamic'

export const POST = bff('audit', async (request, ctx) => {
  const { cohortId, paperId } = await ctx.params
  const input = await parseBody(submitAuditDecision, request)
  const result = await audit.submitReview(cohortId, paperId, input)
  return Response.json(result, { status: 200 })
})

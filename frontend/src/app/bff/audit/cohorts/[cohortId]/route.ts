import { audit } from '@/lib/bff/audit/service'
import { bff } from '@/lib/bff/core/handler'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async (_request, ctx) => {
  const { cohortId } = await ctx.params
  const cohort = await audit.getCohort(cohortId)
  return Response.json(cohort)
})

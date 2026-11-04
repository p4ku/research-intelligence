import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'
import { resolveDisputeInputSchema } from '@/lib/bff/slr/schema'
import { slr } from '@/lib/bff/slr/service'
import type { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

export const POST = bff('audit', async (req: NextRequest, ctx) => {
  const { disputeId } = await ctx.params
  const body = await parseBody(resolveDisputeInputSchema, req)
  const result = await slr.resolveDispute(disputeId, body)
  return Response.json(result)
})

import { bff } from '@/lib/bff/core/handler'
import { slr } from '@/lib/bff/slr/service'
import type { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

export const POST = bff('audit', async (req: NextRequest, ctx) => {
  const { disputeId } = await ctx.params
  const body = await req.json()
  const result = await slr.resolveDispute(disputeId, body)
  return Response.json(result)
})

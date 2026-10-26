import { bff } from '@/lib/bff/core/handler'
import { slr } from '@/lib/bff/slr/service'
import type { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async (req: NextRequest) => {
  const status = req.nextUrl.searchParams.get('status') || 'all'
  const disputes = await slr.getDisputes(status)
  return Response.json(disputes)
})

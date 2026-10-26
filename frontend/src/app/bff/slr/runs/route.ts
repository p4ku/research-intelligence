import { bff } from '@/lib/bff/core/handler'
import { slr } from '@/lib/bff/slr/service'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async () => {
  const runs = await slr.getRuns()
  return Response.json(runs)
})

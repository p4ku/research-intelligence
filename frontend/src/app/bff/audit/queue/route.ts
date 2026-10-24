import { bff } from '@/lib/bff/core/handler'
import { audit } from '@/lib/bff/audit/service'

export const dynamic = 'force-dynamic'

export const GET = bff('audit', async () => {
  const queue = await audit.getMyQueue()
  return Response.json(queue)
})

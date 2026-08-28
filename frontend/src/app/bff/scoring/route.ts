import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { scoringQuery } from '@/lib/bff/scoring/schema'
import { scoring } from '@/lib/bff/scoring/service'

export const dynamic = 'force-dynamic'

export const GET = bff('scoring', async (request) => {
  const { workspace_id } = parseQuery(scoringQuery, request.nextUrl)
  return Response.json(await scoring.get(workspace_id))
})

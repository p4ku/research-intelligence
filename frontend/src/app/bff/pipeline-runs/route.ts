import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { runsQuery } from '@/lib/bff/pipeline-runs/schema'
import { runs } from '@/lib/bff/pipeline-runs/service'

export const dynamic = 'force-dynamic'

export const GET = bff('pipeline-runs', async (request) =>
  Response.json(await runs.list(parseQuery(runsQuery, request.nextUrl))),
)

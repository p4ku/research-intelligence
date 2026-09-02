import { componentRunsQuery } from '@/lib/bff/component-runs/schema'
import { componentRuns } from '@/lib/bff/component-runs/service'
import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'

export const dynamic = 'force-dynamic'

export const GET = bff('component-runs', async (request) =>
  Response.json(await componentRuns.list(parseQuery(componentRunsQuery, request.nextUrl))),
)

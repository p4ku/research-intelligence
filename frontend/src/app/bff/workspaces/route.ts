import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { workspacesQuery } from '@/lib/bff/workspaces/schema'
import { workspaces } from '@/lib/bff/workspaces/service'

export const dynamic = 'force-dynamic'

export const GET = bff('workspaces', async (request) =>
  Response.json(await workspaces.list(parseQuery(workspacesQuery, request.nextUrl))),
)

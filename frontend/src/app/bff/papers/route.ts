import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { papersQuery } from '@/lib/bff/papers/schema'
import { papers } from '@/lib/bff/papers/service'

export const dynamic = 'force-dynamic'

export const GET = bff('papers', async (request) =>
  Response.json(await papers.list(parseQuery(papersQuery, request.nextUrl))),
)

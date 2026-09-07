import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { searchQuery } from '@/lib/bff/search/schema'
import { search } from '@/lib/bff/search/service'

export const dynamic = 'force-dynamic'

export const GET = bff('search', async (request) =>
  Response.json(await search.run(parseQuery(searchQuery, request.nextUrl))),
)

import { editionsQuery } from '@/lib/bff/briefings/schema'
import { briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { getLang } from '@/lib/i18n-server'

export const dynamic = 'force-dynamic'

export const GET = bff('briefings', async (request) =>
  Response.json(await briefings.list(parseQuery(editionsQuery, request.nextUrl), await getLang())),
)

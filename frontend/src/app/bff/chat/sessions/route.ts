import { sessionsQuery } from '@/lib/bff/chat/schema'
import { chat } from '@/lib/bff/chat/service'
import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'

export const dynamic = 'force-dynamic'

export const GET = bff('chat', async (request) =>
  Response.json(await chat.listSessions(parseQuery(sessionsQuery, request.nextUrl))),
)

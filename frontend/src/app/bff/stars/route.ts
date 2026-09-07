import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'
import { starUpdate } from '@/lib/bff/stars/schema'
import { stars } from '@/lib/bff/stars/service'

export const dynamic = 'force-dynamic'

export const GET = bff('stars', async () => Response.json(await stars.get()))

export const PUT = bff('stars', async (request) =>
  Response.json(await stars.set(await parseBody(starUpdate, request))),
)

import { editionQueryOf } from '@/lib/bff/briefings/edition-query'
import { assertDate, briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { getLang } from '@/lib/i18n-server'

export const dynamic = 'force-dynamic'

export const GET = bff('briefings', async (request, ctx) => {
  const { date } = await ctx.params
  const { workspace_id, run_id } = editionQueryOf(request)
  const found = await briefings.findByDate(assertDate(date), await getLang(), workspace_id, run_id)
  if (!found) throw problem('not-found', { detail: 'No briefing for that day.' })
  return Response.json(found)
})

import { editionQuery } from '@/lib/bff/briefings/schema'
import { assertDate, briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { parseQuery } from '@/lib/bff/core/validate'
import { getLang } from '@/lib/i18n-server'

export const dynamic = 'force-dynamic'

export const GET = bff('briefings', async (request, ctx) => {
  const { date } = await ctx.params
  // `?workspace_id=` and `?run_id=` left empty mean "not given" — every
  // domain, the day's newest — not a malformed id.
  const url = new URL(request.nextUrl)
  for (const [key, value] of [...url.searchParams]) if (value === '') url.searchParams.delete(key)
  const { workspace_id, run_id } = parseQuery(editionQuery, url)
  const found = await briefings.findByDate(assertDate(date), await getLang(), workspace_id, run_id)
  if (!found) throw problem('not-found', { detail: 'No briefing for that day.' })
  return Response.json(found)
})

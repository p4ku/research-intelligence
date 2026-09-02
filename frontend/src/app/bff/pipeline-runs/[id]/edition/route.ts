import { briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { assertUuid } from '@/lib/bff/core/validate'
import { getLang } from '@/lib/i18n-server'

export const dynamic = 'force-dynamic'

/** The edition one completed run produced; 404 when the run has none. */
export const GET = bff('pipeline-runs', async (_request, ctx) => {
  const { id } = await ctx.params
  const found = await briefings.forRun(assertUuid(id, 'run id'), await getLang())
  if (!found) throw problem('not-found', { detail: 'This run produced no edition.' })
  return Response.json(found)
})

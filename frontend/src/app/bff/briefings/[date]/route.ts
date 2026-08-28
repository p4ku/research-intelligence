import { assertDate, briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'

export const dynamic = 'force-dynamic'

export const GET = bff('briefings', async (request, ctx) => {
  const { date } = await ctx.params
  const workspaceId = request.nextUrl.searchParams.get('workspace_id')
  if (!workspaceId) throw problem('validation', { detail: 'workspace_id is required.' })
  const found = await briefings.getByDate(workspaceId, assertDate(date))
  if (!found) throw problem('not-found', { detail: 'No briefing for that day.' })
  return Response.json(found)
})

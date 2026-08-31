import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { papers } from '@/lib/bff/papers/service'

export const dynamic = 'force-dynamic'

export const GET = bff('papers', async (_request, ctx) => {
  const { id } = await ctx.params
  const found = await papers.get(id)
  if (!found) throw problem('not-found', { detail: 'No such paper in your workspaces.' })
  return Response.json(found)
})

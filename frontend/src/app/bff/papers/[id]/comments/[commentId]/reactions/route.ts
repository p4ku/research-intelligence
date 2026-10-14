import { comments } from '@/lib/bff/comments/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'

export const dynamic = 'force-dynamic'

export const POST = bff('papers', async (request, ctx) => {
  const { commentId } = await ctx.params
  const body = (await request.json()) as { reaction_type?: string }
  if (typeof body?.reaction_type !== 'string' || !body.reaction_type.trim()) {
    throw problem('validation', { detail: 'reaction_type is required.' })
  }
  const result = await comments.toggleReaction(commentId, body.reaction_type.trim())
  return Response.json(result)
})

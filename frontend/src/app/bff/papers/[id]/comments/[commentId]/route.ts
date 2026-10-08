import { comments } from '@/lib/bff/comments/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'

export const dynamic = 'force-dynamic'

export const PATCH = bff('papers', async (request, ctx) => {
  const { commentId } = await ctx.params
  const body = (await request.json()) as { content?: string }
  if (typeof body?.content !== 'string' || !body.content.trim()) {
    throw problem('validation', { detail: 'Comment content cannot be empty.' })
  }
  const updated = await comments.update(commentId, body.content.trim())
  return Response.json(updated)
})

export const DELETE = bff('papers', async (_request, ctx) => {
  const { commentId } = await ctx.params
  await comments.delete(commentId)
  return new Response(null, { status: 204 })
})

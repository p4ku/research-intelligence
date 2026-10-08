import { comments } from '@/lib/bff/comments/service'
import { bff } from '@/lib/bff/core/handler'

export const dynamic = 'force-dynamic'

export const DELETE = bff('papers', async (_request, ctx) => {
  const { commentId } = await ctx.params
  await comments.delete(commentId)
  return new Response(null, { status: 204 })
})

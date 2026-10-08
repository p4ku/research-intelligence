import { createCommentBody } from '@/lib/bff/comments/schema'
import { comments } from '@/lib/bff/comments/service'
import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'

export const dynamic = 'force-dynamic'

export const GET = bff('papers', async (_request, ctx) => {
  const { id } = await ctx.params
  const list = await comments.list(id)
  return Response.json({ comments: list, count: list.length })
})

export const POST = bff('papers', async (request, ctx) => {
  const { id } = await ctx.params
  const { content } = await parseBody(createCommentBody, request)
  const created = await comments.create(id, content)
  return Response.json(created, { status: 201 })
})

export const DELETE = bff('papers', async (request) => {
  const commentId = request.nextUrl.searchParams.get('commentId')
  if (commentId) {
    await comments.delete(commentId)
    return new Response(null, { status: 204 })
  }
  return new Response(null, { status: 400 })
})

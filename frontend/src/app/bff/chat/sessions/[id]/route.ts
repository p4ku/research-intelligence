import { renameRequest } from '@/lib/bff/chat/schema'
import { chat } from '@/lib/bff/chat/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { parseBody } from '@/lib/bff/core/validate'

export const dynamic = 'force-dynamic'

export const GET = bff('chat', async (_request, ctx) => {
  const { id } = await ctx.params
  const session = await chat.getSession(id)
  if (!session) throw problem('not-found', { detail: 'No such chat session.' })
  return Response.json(session)
})

export const DELETE = bff('chat', async (_request, ctx) => {
  const { id } = await ctx.params
  await chat.deleteSession(id)
  return new Response(null, { status: 204 })
})

export const PATCH = bff('chat', async (request, ctx) => {
  const { id } = await ctx.params
  const { title } = await parseBody(renameRequest, request)
  await chat.renameSession(id, title) // throws 501 until Django's PATCH saves
  return Response.json({ ok: true })
})

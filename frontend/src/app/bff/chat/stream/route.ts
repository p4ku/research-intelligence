import { bff } from '@/lib/bff/core/handler'
import { fromUpstream, problem } from '@/lib/bff/core/problem'
import { sourceOf } from '@/lib/bff/core/source'
import { parseBody } from '@/lib/bff/core/validate'
import { fixtureStreamFrames } from '@/lib/bff/chat/fixtures'
import { pumpChatStream } from '@/lib/bff/chat/reframe'
import { chatStreamRequest, type ChatScope, type PaperCitation } from '@/lib/bff/chat/schema'
import { papers } from '@/lib/bff/papers/service'
import { apiFetch } from '@/lib/api/server'
import { SseWriter } from '@/lib/sse/writer'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const SSE_HEADERS = {
  'content-type': 'text/event-stream; charset=utf-8',
  'cache-control': 'no-cache, no-transform',
  'x-accel-buffering': 'no',
} as const

export const POST = bff('chat', async (request) => {
  const body = await parseBody(chatStreamRequest, request)

  if (sourceOf('chat') === 'stub') return stubStream()

  // Resolve the scope up front: paper scope also yields the one citation the
  // answer is grounded in (Django emits none of its own yet).
  let scope: ChatScope
  let citation: PaperCitation | null = null
  if (body.paper_id) {
    const found = await papers.get(body.paper_id)
    if (!found) throw problem('not-found', { detail: 'No such paper in your workspaces.' })
    scope = { workspace_id: found.paper.workspace_id, paper_id: found.paper.id }
    citation = {
      paper_id: found.paper.id,
      title: found.paper.title,
      signal_score: found.paper.signal_score,
      href: `/papers/${found.paper.id}`,
    }
  } else {
    scope = { workspace_id: body.workspace_id!, paper_id: null }
  }

  const upstreamAbort = new AbortController()
  request.signal.addEventListener('abort', () => upstreamAbort.abort())

  let upstream: Response
  try {
    upstream = await apiFetch('/api/chat/stream/', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        question: body.question,
        paper_id: body.paper_id,
        workspace_id: body.paper_id ? undefined : body.workspace_id,
        session_id: body.session_id,
        deep_thinking: body.deep_thinking,
      }),
      signal: upstreamAbort.signal,
    })
  } catch {
    throw problem('upstream-unavailable', { detail: 'Django did not respond (/api/chat/stream/).' })
  }
  if (!upstream.ok) {
    // Pre-stream failures are plain problem+json, not SSE.
    const text = await upstream.text()
    let parsed: unknown = text
    try {
      parsed = JSON.parse(text)
    } catch {
      /* keep text */
    }
    throw fromUpstream(upstream.status, parsed)
  }
  if (!upstream.headers.get('content-type')?.startsWith('text/event-stream') || !upstream.body) {
    throw problem('upstream-shape', { detail: 'Expected an SSE response from /api/chat/stream/.' })
  }

  const upstreamBody = upstream.body
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const writer = new SseWriter(controller)
      writer.startHeartbeat()
      void pumpChatStream(upstreamBody, writer, {
        scope,
        citation,
        signal: upstreamAbort.signal,
      }).finally(() => writer.close())
    },
    cancel() {
      upstreamAbort.abort()
    },
  })
  return new Response(stream, { headers: SSE_HEADERS })
})

/** Offline development: replay the fixture frames with small delays. */
function stubStream(): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const writer = new SseWriter(controller)
      writer.startHeartbeat()
      let delay = 300
      for (const frame of fixtureStreamFrames) {
        setTimeout(() => writer.frame(frame.event, frame.data), delay)
        delay += frame.event === 'delta' ? 350 : 120
      }
      setTimeout(() => writer.close(), delay + 100)
    },
  })
  return new Response(stream, { headers: SSE_HEADERS })
}

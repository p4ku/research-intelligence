/**
 * Re-frames Django's chat SSE into OUR contract (src/lib/bff/chat/schema.ts):
 * same event names, documented payload shapes, `id:` lines and heartbeats
 * added by the SseWriter, problem+json error payloads. Server-only.
 */
import 'server-only'

import { parseSse } from '@/lib/sse/parse'
import type { SseWriter } from '@/lib/sse/writer'
import { problemBody } from '../core/problem'
import type { ChatScope, ChatUsage, PaperCitation } from './schema'
import { visualCitation } from './schema'
import { djangoChatEvent } from './upstream'

export interface ReframeOptions {
  scope: ChatScope
  /**
   * Paper-scope streams cite the session's one paper; Django emits no
   * citations of its own yet (the requested `citations` event covers
   * workspace scope).
   */
  citation: PaperCitation | null
  signal?: AbortSignal
}

export async function pumpChatStream(
  upstream: ReadableStream<Uint8Array>,
  writer: SseWriter,
  { scope, citation, signal }: ReframeOptions,
): Promise<void> {
  let sessionId: string | null = null
  let messageId: string | null = null
  try {
    for await (const frame of parseSse(upstream, signal)) {
      let data: unknown
      try {
        data = JSON.parse(frame.data)
      } catch {
        continue // Not JSON (e.g. a stray comment-like line) — skip.
      }
      const parsed = djangoChatEvent.safeParse({ event: frame.event, data })
      if (!parsed.success) continue // Unknown event name or drifted payload — skip.
      const event = parsed.data
      switch (event.event) {
        case 'metadata': {
          sessionId = event.data.session_id
          messageId = event.data.message_id
          writer.frame('metadata', { message_id: messageId, session_id: sessionId, scope })
          if (citation) writer.frame('citations', { items: [citation] })
          break
        }
        case 'delta':
          writer.frame('delta', { text: event.data.delta })
          break
        case 'citations':
          // Requested of Django (workspace scope); passed through once it exists.
          writer.frame('citations', { items: event.data.citations })
          break
        case 'visual_citations': {
          const items = event.data.visual_citations
            .map((v) => visualCitation.safeParse(v))
            .filter((r) => r.success)
            .map((r) => r.data)
          if (items.length > 0) writer.frame('visual_citations', { items })
          break
        }
        case 'fact_check': {
          const guard = event.data.hallucination_guard
          if (guard && typeof guard === 'object' && Object.keys(guard).length > 0) {
            writer.frame('fact_check', guard)
          }
          break
        }
        case 'usage': {
          const usage: ChatUsage = {
            tokens_in: event.data.tokens_in ?? null,
            tokens_out: event.data.tokens_out ?? null,
            total_tokens: event.data.total_tokens ?? null,
            usd_cost:
              event.data.usd_cost === null || event.data.usd_cost === undefined
                ? null
                : Number(event.data.usd_cost),
          }
          writer.frame('usage', usage)
          break
        }
        case 'done':
          writer.frame('done', {
            message_id: event.data.message_id ?? messageId,
            session_id: sessionId,
          })
          return
        case 'error':
          writer.frame(
            'error',
            problemBody('upstream-error', { detail: event.data.error }),
          )
          return
      }
    }
    // Upstream ended without done/error (connection cut): tell the client.
    writer.frame(
      'error',
      problemBody('upstream-error', { detail: 'The backend stream ended unexpectedly.' }),
    )
  } catch (error) {
    if (signal?.aborted) return
    writer.frame(
      'error',
      problemBody('upstream-error', {
        detail: `The backend stream failed: ${String(error).slice(0, 200)}`,
      }),
    )
  }
}

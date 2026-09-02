/**
 * The pure half of the chat-stream client: reduces our SSE frames
 * (src/lib/bff/chat/schema.ts) into sink calls and decides how the stream
 * ended. Extracted from use-chat-stream so the terminal decision — a cut
 * stream must never pass for a completed answer — is unit-testable with a
 * mocked ReadableStream, no DOM required.
 */
import type {
  ChatScope,
  ChatUsage,
  FactCheck,
  PaperCitation,
  VisualCitation,
} from '@/lib/bff/chat/schema'
import type { Problem } from '@/lib/bff/core/problem'
import { parseSse } from '@/lib/sse/parse'

export type ChatStreamStatus = 'idle' | 'connecting' | 'streaming' | 'done' | 'error'

export interface ChatStreamState {
  status: ChatStreamStatus
  text: string
  sessionId: string | null
  messageId: string | null
  scope: ChatScope | null
  citations: PaperCitation[]
  visualCitations: VisualCitation[]
  factCheck: FactCheck | null
  usage: ChatUsage | null
  error: Problem | null
}

/** How a chat stream ended. The consumer owns what each ending means. */
export type StreamEnd =
  | { kind: 'done' } // a done frame arrived
  | { kind: 'error'; problem: Problem } // an explicit error frame arrived
  | { kind: 'aborted' } // the signal fired; say nothing
  | { kind: 'cut' } // closed or threw with no done frame

export interface StreamSink {
  /** Non-terminal fields only — consuming a stream can never settle state. */
  patch(fields: Partial<Omit<ChatStreamState, 'status' | 'text' | 'error'>>): void
  delta(text: string): void
}

/**
 * Pump one SSE body into the sink and report the ending. Never throws: an
 * exception mid-stream is `aborted` when the signal fired (the reader rejects
 * on abort) and `cut` otherwise. A close without a `done` frame is `cut` —
 * SSE has an explicit terminator, and its absence is a failure, not an end.
 */
export async function consumeChatStream(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
  sink: StreamSink,
): Promise<StreamEnd> {
  let sawDone = false
  try {
    for await (const frame of parseSse(body, signal)) {
      let data: unknown
      try {
        data = JSON.parse(frame.data)
      } catch {
        continue
      }
      const record = data as Record<string, unknown>
      switch (frame.event) {
        case 'metadata':
          sink.patch({
            sessionId: (record.session_id as string) ?? null,
            messageId: (record.message_id as string) ?? null,
            scope: (record.scope as ChatScope) ?? null,
          })
          break
        case 'delta':
          sink.delta((record.text as string) ?? '')
          break
        case 'citations':
          sink.patch({ citations: (record.items as PaperCitation[]) ?? [] })
          break
        case 'visual_citations':
          sink.patch({ visualCitations: (record.items as VisualCitation[]) ?? [] })
          break
        case 'fact_check':
          sink.patch({ factCheck: record as unknown as FactCheck })
          break
        case 'usage':
          sink.patch({ usage: record as unknown as ChatUsage })
          break
        case 'done':
          sawDone = true
          break
        case 'error':
          return { kind: 'error', problem: record as unknown as Problem }
      }
      if (sawDone) break
    }
  } catch {
    return signal.aborted ? { kind: 'aborted' } : { kind: 'cut' }
  }
  if (signal.aborted) return { kind: 'aborted' }
  return sawDone ? { kind: 'done' } : { kind: 'cut' }
}

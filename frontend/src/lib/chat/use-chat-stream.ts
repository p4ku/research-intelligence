'use client'

/**
 * The client half of the chat contract: POSTs to /bff/chat/stream and reduces
 * our SSE frames (src/lib/bff/chat/schema.ts) into render state. Replaces the
 * old use-simulated-stream. Delta text is batched through rAF so chunky
 * streams don't render per token.
 */
import type {
  ChatScope,
  ChatStreamRequest,
  ChatUsage,
  FactCheck,
  PaperCitation,
  VisualCitation,
} from '@/lib/bff/chat/schema'
import type { Problem } from '@/lib/bff/core/problem'
import { parseSse } from '@/lib/sse/parse'
import { useCallback, useEffect, useReducer, useRef } from 'react'

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

const INITIAL: ChatStreamState = {
  status: 'idle',
  text: '',
  sessionId: null,
  messageId: null,
  scope: null,
  citations: [],
  visualCitations: [],
  factCheck: null,
  usage: null,
  error: null,
}

type Action =
  | { type: 'connect' }
  | { type: 'patch'; patch: Partial<ChatStreamState> }
  | { type: 'reset' }

function reducer(state: ChatStreamState, action: Action): ChatStreamState {
  switch (action.type) {
    case 'connect':
      return { ...INITIAL, status: 'connecting' }
    case 'patch':
      return { ...state, ...action.patch }
    case 'reset':
      return INITIAL
  }
}

export function useChatStream(onFinish?: (final: ChatStreamState) => void) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const abortRef = useRef<AbortController | null>(null)
  const textRef = useRef('')
  const flushRef = useRef(0)
  // Mirror of the reducer state so the async loop can hand a complete
  // snapshot to onFinish without waiting for a render.
  const snapshotRef = useRef<ChatStreamState>(INITIAL)
  const onFinishRef = useRef(onFinish)
  onFinishRef.current = onFinish

  const patch = useCallback((patch: Partial<ChatStreamState>) => {
    snapshotRef.current = { ...snapshotRef.current, ...patch }
    dispatch({ type: 'patch', patch })
  }, [])

  const flushText = useCallback(() => {
    if (flushRef.current) return
    flushRef.current = requestAnimationFrame(() => {
      flushRef.current = 0
      patch({ status: 'streaming', text: textRef.current })
    })
  }, [patch])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (request: ChatStreamRequest) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      textRef.current = ''
      snapshotRef.current = { ...INITIAL, status: 'connecting' }
      dispatch({ type: 'connect' })

      const fail = (error: Problem) => {
        patch({ status: 'error', error, text: textRef.current })
        onFinishRef.current?.(snapshotRef.current)
      }

      let res: Response
      try {
        res = await fetch('/bff/chat/stream', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(request),
          signal: controller.signal,
        })
      } catch {
        if (controller.signal.aborted) return
        return fail({
          type: '/problems/upstream-unavailable',
          title: 'Connection failed',
          status: 0,
        })
      }
      if (!res.ok || !res.body) {
        const problem = (await res.json().catch(() => null)) as Problem | null
        if (problem?.status === 401) window.location.assign('/auth/logout?reason=expired')
        return fail(
          problem ?? {
            type: '/problems/internal',
            title: `HTTP ${res.status}`,
            status: res.status,
          },
        )
      }

      try {
        for await (const frame of parseSse(res.body, controller.signal)) {
          let data: unknown
          try {
            data = JSON.parse(frame.data)
          } catch {
            continue
          }
          const record = data as Record<string, unknown>
          switch (frame.event) {
            case 'metadata':
              patch({
                sessionId: (record.session_id as string) ?? null,
                messageId: (record.message_id as string) ?? null,
                scope: (record.scope as ChatScope) ?? null,
              })
              break
            case 'delta':
              textRef.current += (record.text as string) ?? ''
              flushText()
              break
            case 'citations':
              patch({ citations: (record.items as PaperCitation[]) ?? [] })
              break
            case 'visual_citations':
              patch({ visualCitations: (record.items as VisualCitation[]) ?? [] })
              break
            case 'fact_check':
              patch({ factCheck: record as unknown as FactCheck })
              break
            case 'usage':
              patch({ usage: record as unknown as ChatUsage })
              break
            case 'done':
              if (flushRef.current) cancelAnimationFrame(flushRef.current)
              flushRef.current = 0
              patch({ status: 'done', text: textRef.current })
              break
            case 'error':
              return fail(record as unknown as Problem)
          }
        }
      } catch {
        if (!controller.signal.aborted) {
          return fail({
            type: '/problems/upstream-error',
            title: 'The stream was interrupted',
            status: 502,
          })
        }
      }
      // Stream closed (done, abort, or cut): settle with what we have.
      if (flushRef.current) cancelAnimationFrame(flushRef.current)
      flushRef.current = 0
      patch({ status: 'done', text: textRef.current })
      onFinishRef.current?.(snapshotRef.current)
    },
    [flushText, patch],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    textRef.current = ''
    snapshotRef.current = INITIAL
    dispatch({ type: 'reset' })
  }, [])

  return { state, send, abort, reset }
}

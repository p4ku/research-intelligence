'use client'

/**
 * The client half of the chat contract: POSTs to /bff/chat/stream and reduces
 * our SSE frames into render state. The frame loop and the terminal decision
 * live in consume-stream.ts (pure, unit-tested); this hook maps the ending
 * onto state: `done` settles, an error frame or a cut stream fails with the
 * partial text kept, and an abort says nothing at all — `reset()` and unmount
 * are silent by construction, while `stop()` is the one deliberate
 * settle-with-what-we-have. Delta text is batched through rAF so chunky
 * streams don't render per token.
 */
import type { ChatStreamRequest } from '@/lib/bff/chat/schema'
import { problemBody, type Problem } from '@/lib/bff/core/problem'
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { consumeChatStream, type ChatStreamState } from './consume-stream'

export type { ChatStreamState, ChatStreamStatus } from './consume-stream'

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
  useEffect(() => {
    onFinishRef.current = onFinish
  })

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

  const cancelFlush = useCallback(() => {
    if (flushRef.current) cancelAnimationFrame(flushRef.current)
    flushRef.current = 0
  }, [])

  /**
   * Reader-initiated stop: file what has arrived as a done turn. The status
   * guard makes it idempotent — a stop after settle must not re-fire
   * onFinish. The rAF cancel matters: a queued flush re-patching `streaming`
   * after the done-patch would hang the consumers' reveal handshake.
   */
  const stop = useCallback(() => {
    const status = snapshotRef.current.status
    if (status !== 'connecting' && status !== 'streaming') return
    abortRef.current?.abort()
    abortRef.current = null
    cancelFlush()
    patch({ status: 'done', text: textRef.current })
    onFinishRef.current?.(snapshotRef.current)
  }, [cancelFlush, patch])

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
        return fail(problemBody('upstream-unavailable'))
      }
      if (!res.ok || !res.body) {
        const problem = (await res.json().catch(() => null)) as Problem | null
        // A stop() can race the body read; it already settled — say nothing.
        if (controller.signal.aborted) return
        if (problem?.status === 401) window.location.assign('/auth/logout?reason=expired')
        return fail(problem ?? problemBody(res.status >= 500 ? 'upstream-error' : 'internal'))
      }

      const end = await consumeChatStream(res.body, controller.signal, {
        patch,
        delta: (text) => {
          textRef.current += text
          flushText()
        },
      })
      cancelFlush()
      switch (end.kind) {
        case 'aborted':
          return // reset(), unmount, re-send preemption, or a settled stop(): say nothing
        case 'error':
          return fail(end.problem)
        case 'cut':
          return fail(problemBody('upstream-error')) // no done frame: a truncation, not an ending
        case 'done':
          patch({ status: 'done', text: textRef.current })
          onFinishRef.current?.(snapshotRef.current)
      }
    },
    [cancelFlush, flushText, patch],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    cancelFlush()
    textRef.current = ''
    snapshotRef.current = INITIAL
    dispatch({ type: 'reset' })
  }, [cancelFlush])

  return { state, send, stop, reset }
}

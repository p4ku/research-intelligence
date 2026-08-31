'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import type { ChatSession, ChatSessionDetail, VisualCitation } from '@/lib/bff/chat/schema'
import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import { useChatStream } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { ScoredPaper } from '@/lib/papers/types'
import { PaperAirplaneIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useEffect, useRef, useState } from 'react'

interface Msg {
  role: 'user' | 'scanner'
  text: string
  /** Structured partners of the answer's inline `[Page N, …]` markers. */
  visualCitations: VisualCitation[]
  failed?: boolean
}

/**
 * The side rail on the paper detail page: a plain vertical conversation
 * scoped to this one paper, streamed from POST /bff/chat/stream. The paper's
 * newest session (if any) is loaded on mount and continued. Deliberately
 * bare — history browsing and corpus scope live on the Ask page.
 */
export function PaperChat({ paper }: { paper: ScoredPaper }) {
  const t = useT()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [asking, setAskingState] = useState(false)
  const askingRef = useRef(false)
  const setAsking = (v: boolean) => {
    askingRef.current = v
    setAskingState(v)
  }
  const endRef = useRef<HTMLDivElement>(null)

  // Settle the finished stream into the transcript (runs from the stream
  // loop, not a render effect).
  const { state: live, send } = useChatStream((final) => {
    if (!askingRef.current) return
    const failed = final.status === 'error'
    setMsgs((prev) => [
      ...prev,
      {
        role: 'scanner',
        text: failed
          ? (final.error?.detail ?? final.error?.title ?? t('The answer failed.'))
          : final.text,
        visualCitations: failed ? [] : final.visualCitations,
        failed,
      },
    ])
    if (final.sessionId) setSessionId(final.sessionId)
    setAsking(false)
  })

  // Continue the paper's newest session, if one exists.
  const loaded = useRef(false)
  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    void (async () => {
      try {
        const page = await bffFetch<Page<ChatSession>>(
          `/bff/chat/sessions?paper_id=${paper.id}&page_size=1`,
        )
        const newest = page.results[0]
        if (!newest) return
        const detail = await bffFetch<ChatSessionDetail>(`/bff/chat/sessions/${newest.id}`)
        setSessionId(detail.id)
        setMsgs(
          detail.turns.flatMap((turn): Msg[] => [
            { role: 'user', text: turn.question, visualCitations: [] },
            {
              role: 'scanner',
              text: turn.answer ?? turn.error ?? t('The answer failed.'),
              visualCitations: turn.visual_citations,
              failed: turn.status === 'failed',
            },
          ]),
        )
      } catch {
        // No history — start fresh.
      }
    })()
  }, [paper.id, t])

  useEffect(() => {
    if (msgs.length > 0 || live.text) endRef.current?.scrollIntoView({ block: 'end' })
  }, [msgs, live.text])

  function ask(q: string) {
    if (asking) return
    setMsgs((prev) => [...prev, { role: 'user', text: q, visualCitations: [] }])
    setAsking(true)
    setInput('')
    void send({
      question: q,
      paper_id: paper.id,
      session_id: sessionId ?? undefined,
      deep_thinking: false,
    })
  }

  return (
    <section
      aria-label={fmt(t('Ask about {title}'), { title: paper.title })}
      className="border-line bg-surface flex flex-col overflow-hidden rounded-sm border shadow-xs max-lg:max-h-[32rem] lg:sticky lg:top-8 lg:h-[28rem]"
    >
      <div className="border-line-soft flex items-center gap-2 border-b px-4 py-2.5">
        <span aria-hidden="true" className="bg-accent size-1.5 shrink-0 rounded-full" />
        <span className="text-foreground font-mono text-[11px] font-medium tracking-[0.18em] uppercase">
          {t('Ask this paper')}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {msgs.length === 0 && !asking ? (
          <p className="text-muted-foreground text-sm leading-relaxed text-balance">
            {t('Questions here are answered from this paper alone.')}
          </p>
        ) : (
          <div className="space-y-4">
            {msgs.map((m, i) =>
              m.role === 'user' ? (
                <p
                  key={i}
                  className="text-foreground pt-1 text-[13px] font-semibold tracking-tight text-pretty"
                >
                  {m.text}
                </p>
              ) : m.failed ? (
                // Failure text is an error string, not model prose.
                <p key={i} className="text-warn text-[13px] leading-relaxed whitespace-pre-wrap">
                  {m.text}
                </p>
              ) : (
                <AnswerMarkdown
                  key={i}
                  text={m.text}
                  citations={m.visualCitations}
                  t={t}
                  className="text-muted-foreground text-[13px]"
                />
              ),
            )}
            {asking &&
              (live.text ? (
                <AnswerMarkdown
                  text={live.text}
                  streaming={live.status === 'streaming'}
                  citations={live.visualCitations}
                  t={t}
                  className="text-muted-foreground text-[13px]"
                />
              ) : (
                <p className="text-muted-foreground flex items-center gap-2 font-mono text-xs">
                  <span className="relative flex size-2 shrink-0">
                    <span className="bg-accent/60 absolute inset-0 animate-ping rounded-full" />
                    <span className="bg-accent relative size-2 rounded-full" />
                  </span>
                  {t('Reading the full text…')}
                </p>
              ))}
            <div ref={endRef} aria-hidden="true" />
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim()) ask(input.trim())
        }}
        className="border-line-soft focus-within:border-foreground/20 border-t transition-colors"
      >
        <div className="flex items-center gap-2 p-1.5 pl-4">
          <input
            name="question"
            aria-label={t('Ask a question about this paper')}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('Ask about this paper…')}
            className="text-foreground placeholder:text-muted-foreground min-w-0 flex-1 bg-transparent text-sm focus:outline-none max-sm:text-base"
          />
          <button
            type="submit"
            aria-label={t('Send')}
            disabled={asking}
            className={clsx(
              'focus-visible:outline-accent flex size-8 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2',
              input.trim() && !asking
                ? 'bg-foreground text-background hover:bg-foreground/85'
                : 'bg-foreground/10 text-muted-foreground',
            )}
          >
            <PaperAirplaneIcon className="size-4" />
          </button>
        </div>
      </form>
    </section>
  )
}

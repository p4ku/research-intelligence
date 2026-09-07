'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { ErrorNote } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import type { ChatSession, ChatSessionDetail, VisualCitation } from '@/lib/bff/chat/schema'
import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import { problemMessage } from '@/lib/bff/problem-copy'
import { useChatStream } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { ScoredPaper } from '@/lib/papers/types'
import { PaperAirplaneIcon, XMarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useEffect, useRef, useState, type ReactNode } from 'react'

interface Msg {
  role: 'user' | 'scanner'
  text: string
  /** Structured partners of the answer's inline `[Page N, …]` markers. */
  visualCitations: VisualCitation[]
  /** Mapped problem copy when the turn failed; partial `text` is kept. */
  error?: string | null
}

/**
 * Ask this paper: a pill fixed to the bottom-right of the page that opens a
 * sheet from the right edge with a plain vertical conversation scoped to this
 * one paper, streamed from POST /bff/chat/stream. The paper's newest session
 * (if any) is loaded on mount and continued, so reopening the paper shows the
 * earlier questions. Deliberately bare — history browsing lives on Ask.
 */
export function PaperChat({ paper }: { paper: ScoredPaper }) {
  const t = useT()
  const [open, setOpen] = useState(false)
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
  const inputRef = useRef<HTMLInputElement>(null)

  // Settle the finished stream into the transcript (runs from the stream
  // loop, not a render effect).
  const { state: live, send } = useChatStream((final) => {
    if (!askingRef.current) return
    setMsgs((prev) => [
      ...prev,
      {
        role: 'scanner',
        // A failure keeps what streamed; the error rides alongside the text.
        text: final.text,
        visualCitations: final.visualCitations,
        error: final.status === 'error' ? problemMessage(final.error, t) : null,
      },
    ])
    if (final.sessionId) setSessionId(final.sessionId)
    setAsking(false)
  })

  // Continue the paper's newest session, if one exists. A failed load is a
  // failure, not "no history": it gets its own state and a Retry (bump
  // `reloadKey`), and never dresses up as the empty state.
  const [historyState, setHistoryState] = useState<'loading' | 'empty' | 'ready' | 'failed'>(
    'loading',
  )
  const [reloadKey, setReloadKey] = useState(0)
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const page = await bffFetch<Page<ChatSession>>(
          `/bff/chat/sessions?paper_id=${paper.id}&page_size=1`,
        )
        const newest = page.results[0]
        if (!newest) {
          if (!cancelled) setHistoryState('empty')
          return
        }
        const detail = await bffFetch<ChatSessionDetail>(`/bff/chat/sessions/${newest.id}`)
        if (cancelled) return
        setSessionId(detail.id)
        setMsgs(
          detail.turns.flatMap((turn): Msg[] => [
            { role: 'user', text: turn.question, visualCitations: [] },
            {
              role: 'scanner',
              text: turn.answer ?? '',
              visualCitations: turn.visual_citations,
              error: turn.status === 'failed' ? (turn.error ?? t('The answer failed.')) : null,
            },
          ]),
        )
        setHistoryState('ready')
      } catch (error) {
        console.error('[paper-chat] history load failed:', error)
        if (!cancelled) setHistoryState('failed')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [paper.id, reloadKey, t])

  useEffect(() => {
    if (open && (msgs.length > 0 || live.text)) endRef.current?.scrollIntoView({ block: 'end' })
  }, [open, msgs, live.text])

  // The sheet: focus the composer once it has slid in; Escape closes it.
  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => inputRef.current?.focus(), 260)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

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
    <PaperChatFrame
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      label={fmt(t('Ask about {title}'), { title: paper.title })}
      title={t('Ask this paper')}
      subtitle={paper.title}
      body={
        msgs.length === 0 && !asking && historyState !== 'failed' ? (
          <p className="text-sm leading-relaxed text-balance text-muted-foreground">
            {t('Questions here are answered from this paper alone.')}
          </p>
        ) : (
          <div className="space-y-4">
            {msgs.map((m, i) =>
              m.role === 'user' ? (
                <p
                  key={i}
                  className="pt-1 text-[13px] font-semibold tracking-tight text-pretty text-foreground"
                >
                  {m.text}
                </p>
              ) : (
                <div key={i} className="min-w-0">
                  {m.text !== '' && (
                    <AnswerMarkdown
                      text={m.text}
                      citations={m.visualCitations}
                      t={t}
                      className={clsx('text-[13px] text-muted-foreground', m.error && 'mb-2')}
                    />
                  )}
                  {m.error && (
                    <ErrorNote className="whitespace-pre-wrap">
                      {m.text !== '' ? t('The answer stopped part-way through.') : m.error}
                    </ErrorNote>
                  )}
                </div>
              ),
            )}
            {asking &&
              (live.text ? (
                <AnswerMarkdown
                  text={live.text}
                  streaming={live.status === 'streaming'}
                  citations={live.visualCitations}
                  t={t}
                  className="text-[13px] text-muted-foreground"
                />
              ) : (
                <p className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
                  <span className="relative flex size-2 shrink-0">
                    <span className="absolute inset-0 animate-ping rounded-full bg-accent/60" />
                    <span className="relative size-2 rounded-full bg-accent" />
                  </span>
                  {t('Generating…')}
                </p>
              ))}
            <div ref={endRef} aria-hidden="true" />
          </div>
        )
      }
      footer={
        <>
          {historyState === 'failed' && msgs.length === 0 && (
            <div className="border-t border-line-soft px-4 py-3">
              <ErrorNote
                action={
                  <button
                    type="button"
                    onClick={() => {
                      setHistoryState('loading')
                      setReloadKey((k) => k + 1)
                    }}
                    className="rounded-sm bg-foreground px-2.5 py-1 text-xs font-medium text-background transition-colors hover:bg-foreground/85"
                  >
                    {t('Retry')}
                  </button>
                }
              >
                {t("Couldn't load this paper's earlier questions.")}{' '}
                {t('A new thread will start if you ask now.')}
              </ErrorNote>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (input.trim()) ask(input.trim())
            }}
            className="border-t border-line-soft transition-colors focus-within:border-foreground/20"
          >
            <div className="flex items-center gap-2 p-1.5 pl-4">
              <input
                ref={inputRef}
                name="question"
                aria-label={t('Ask a question about this paper')}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t('Ask a question about this paper…')}
                className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none max-sm:text-base"
              />
              <button
                type="submit"
                aria-label={t('Send')}
                disabled={asking}
                className={clsx(
                  'flex size-8 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                  input.trim() && !asking
                    ? 'bg-foreground text-background hover:bg-foreground/85'
                    : 'bg-foreground/10 text-muted-foreground',
                )}
              >
                <PaperAirplaneIcon className="size-4" />
              </button>
            </div>
          </form>
        </>
      }
    />
  )
}

const PILL_CLASS =
  'bg-foreground text-background fixed right-6 bottom-6 z-30 inline-flex h-11 items-center gap-2.5 rounded-full pr-[18px] pl-3.5 text-[13.5px] font-medium shadow-[0_8px_24px_-6px_rgba(19,19,17,0.35)] transition-[transform,opacity] duration-150 ease-out'

/**
 * The chat's chrome: the pill, and the sheet it opens — header strip with
 * the title, the scrolling body, and whatever sits under
 * it (the composer, an error). PaperChat and PaperChatSkeleton both fill it.
 * The sheet stays mounted (translated off-screen) so the thread keeps its
 * scroll position between opens.
 */
export function PaperChatFrame({
  state = 'loaded',
  open = false,
  onOpen,
  onClose,
  label,
  title,
  subtitle,
  body,
  footer,
}: {
  state?: 'loaded' | 'skeleton'
  open?: boolean
  onOpen?: () => void
  onClose?: () => void
  label: string
  title: string
  subtitle?: ReactNode
  body: ReactNode
  footer: ReactNode
}) {
  return (
    <>
      <button
        type="button"
        data-shape="paper-chat-pill"
        data-state={state}
        onClick={onOpen}
        disabled={!onOpen}
        aria-expanded={open}
        className={clsx(PILL_CLASS, 'active:scale-[0.97]', open && 'pointer-events-none opacity-0')}
      >
        <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
        {title}
      </button>

      <aside
        aria-label={label}
        aria-hidden={!open}
        data-shape="paper-chat"
        data-state={state}
        className={clsx(
          'fixed inset-y-0 right-0 z-40 flex w-full max-w-[440px] flex-col border-l border-line-strong bg-surface shadow-[-12px_0_40px_-16px_rgba(19,19,17,0.25)] transition-transform duration-[260ms] ease-out motion-reduce:transition-none',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line-soft py-3 pr-3 pl-[18px]">
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase">
              <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-accent" />
              {title}
            </div>
            {subtitle && (
              <div className="mt-0.5 truncate text-xs text-zinc-400 dark:text-zinc-500">
                {subtitle}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={!onClose}
            aria-label="Close"
            className="rounded-sm p-1.5 text-zinc-500 transition-colors hover:bg-line-soft"
          >
            <XMarkIcon aria-hidden="true" className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-[18px] py-4">{body}</div>

        {footer}
      </aside>
    </>
  )
}

/** Before the record arrives: the pill, and the sheet closed with a bone hint. */
export function PaperChatSkeleton({ label, title }: { label: string; title: string }) {
  return (
    <PaperChatFrame
      state="skeleton"
      label={label}
      title={title}
      body={
        <p className="text-sm leading-relaxed text-muted-foreground">
          <Bone.Text lines={2} widths={['92%', '48%']} />
        </p>
      }
      footer={
        <div className="border-t border-line-soft">
          <div className="flex items-center gap-2 p-1.5 pl-4">
            <span className="min-w-0 flex-1 text-sm max-sm:text-base">
              <Bone.Text widths={['20ch']} />
            </span>
            <Bone.Block className="size-8" round />
          </div>
        </div>
      }
    />
  )
}

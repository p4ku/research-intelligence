'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { LiveAnswer } from '@/components/live-answer'
import { Card, ErrorNote } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import type { VisualCitation } from '@/lib/bff/chat/schema'
import { problemMessage } from '@/lib/bff/problem-copy'
import { useChatStream, type ChatStreamState } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { ScoredPaper } from '@/lib/papers/types'
import { ChatBubbleLeftRightIcon, PaperAirplaneIcon, XMarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useReducedMotion } from 'motion/react'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react'

interface Msg {
  role: 'user' | 'scanner'
  text: string
  /** Structured partners of the answer's inline `[Page N, …]` markers. */
  visualCitations: VisualCitation[]
  /** Mapped problem copy when the turn failed; partial `text` is kept. */
  error?: string | null
}

/**
 * Ask this paper: a composer card under the score rail where the first
 * question is typed, and a sheet from the right edge that opens with that
 * question asked — a plain vertical conversation scoped to this one paper,
 * streamed from POST /bff/chat/stream. On narrow screens the rail stacks
 * under the record, so a pill fixed to the bottom-right opens the sheet
 * empty instead. Every open is a new conversation: closing the sheet drops
 * the thread and the session with it, so the next open starts empty.
 * Deliberately bare — history lives on Ask.
 */
export function PaperChat({ paper }: { paper: ScoredPaper }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  // The rail composer's own draft: it survives a closed sheet, the sheet's does not.
  const [draft, setDraft] = useState('')
  const [asking, setAskingState] = useState(false)
  const askingRef = useRef(false)
  const setAsking = (v: boolean) => {
    askingRef.current = v
    setAskingState(v)
  }
  // Bumps per question so the live answer mounts fresh (its reveal position
  // is never reset, only clamped).
  const [askSeq, setAskSeq] = useState(0)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const reduceMotion = useReducedMotion()

  const follow = useCallback(() => endRef.current?.scrollIntoView({ block: 'end' }), [])

  // As on Ask, a stream settles into the transcript once two things are
  // true: the stream has finished (finalRef) and the reveal has shown every
  // word (revealedRef). Either can come first.
  const finalRef = useRef<ChatStreamState | null>(null)
  const revealedRef = useRef(false)

  const commit = useCallback(
    (final: ChatStreamState) => {
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
    },
    [t],
  )

  const trySettle = useCallback(() => {
    const final = finalRef.current
    if (!final || !revealedRef.current || !askingRef.current) return
    finalRef.current = null
    revealedRef.current = false
    // Let the last words finish unveiling before the settled text takes over.
    const delay = reduceMotion || final.status === 'error' ? 0 : 600
    window.setTimeout(() => commit(final), delay)
  }, [commit, reduceMotion])

  const {
    state: live,
    send,
    reset,
  } = useChatStream((final) => {
    if (!askingRef.current) return
    finalRef.current = final
    trySettle()
  })

  const onRevealed = useCallback(() => {
    revealedRef.current = true
    trySettle()
  }, [trySettle])

  /**
   * A sitting, not a thread. Opening clears the transcript and the session id
   * so the next question starts a new conversation; closing drops an answer
   * still streaming rather than letting it write into a transcript nobody
   * will see again.
   */
  function openChat() {
    setMsgs([])
    setSessionId(null)
    setInput('')
    setOpen(true)
  }

  const closeChat = useCallback(() => {
    setOpen(false)
    if (askingRef.current) {
      finalRef.current = null
      revealedRef.current = false
      reset()
      setAsking(false)
    }
  }, [reset])

  useEffect(() => {
    if (open && msgs.length > 0) follow()
  }, [open, msgs, follow])

  // The sheet: focus the composer once it has slid in; Escape closes it.
  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => inputRef.current?.focus(), 260)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeChat()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, closeChat])

  /**
   * `session` is the conversation to continue — this render's, unless the
   * caller knows state has not landed yet (the rail opens a new sitting and
   * asks in the same tick, so it passes null rather than the last one's id).
   */
  function ask(q: string, session: string | null = sessionId) {
    if (asking) return
    setMsgs((prev) => [...prev, { role: 'user', text: q, visualCitations: [] }])
    setAsking(true)
    setAskSeq((n) => n + 1)
    setInput('')
    void send({
      question: q,
      paper_id: paper.id,
      session_id: session ?? undefined,
      deep_thinking: false,
    })
  }

  /**
   * The rail composer: a question typed under the score opens the sheet
   * with it already asked — always the first turn of a new sitting, so the
   * previous sitting's session id is not carried over. Guarded by the refs,
   * not the render's values: the sheet may have opened this same tick.
   */
  function askFromRail(e: FormEvent) {
    e.preventDefault()
    const q = draft.trim()
    if (!q || open || askingRef.current) return
    openChat()
    ask(q, null)
    setDraft('')
  }

  return (
    <PaperChatFrame
      open={open}
      onOpen={openChat}
      onClose={closeChat}
      label={fmt(t('Ask about {title}'), { title: paper.title })}
      title={t('Ask this paper')}
      subtitle={paper.title}
      hint={t('Answered from this paper alone.')}
      composer={
        <Composer
          name="rail-question"
          value={draft}
          onChange={setDraft}
          onSubmit={askFromRail}
          placeholder={t('What would you like to know?')}
          label={t('Ask a question about this paper')}
          send={t('Send')}
          disabled={open}
        />
      }
      body={
        msgs.length === 0 && !asking ? (
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
            {asking && (
              <LiveAnswer
                key={askSeq}
                state={live}
                scanning={t('Reading the full text…')}
                className="text-[13px] text-muted-foreground"
                onGrow={follow}
                onRevealed={onRevealed}
              />
            )}
            <div ref={endRef} aria-hidden="true" />
          </div>
        )
      }
      footer={
        <Composer
          inputRef={inputRef}
          name="question"
          value={input}
          onChange={setInput}
          onSubmit={(e) => {
            e.preventDefault()
            if (input.trim()) ask(input.trim())
          }}
          placeholder={t('Ask a question about this paper…')}
          label={t('Ask a question about this paper')}
          send={t('Send')}
          disabled={asking}
        />
      }
    />
  )
}

/**
 * One question line with a send button, under a hairline — the same row in
 * the rail card and at the foot of the sheet. `disabled` holds the send
 * (an answer streaming, or the sheet already open) while the text stays
 * editable.
 */
function Composer({
  inputRef,
  name,
  value,
  onChange,
  onSubmit,
  placeholder,
  label,
  send,
  disabled = false,
}: {
  inputRef?: RefObject<HTMLInputElement | null>
  name: string
  value: string
  onChange: (value: string) => void
  onSubmit: (e: FormEvent) => void
  placeholder: string
  label: string
  send: string
  disabled?: boolean
}) {
  const ready = value.trim() !== '' && !disabled
  return (
    <form
      onSubmit={onSubmit}
      className="border-t border-line-soft transition-colors focus-within:border-foreground/20"
    >
      <div className="flex items-center gap-2 p-1.5 pl-4">
        <input
          ref={inputRef}
          name={name}
          aria-label={label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none max-sm:text-base"
        />
        <button
          type="submit"
          aria-label={send}
          disabled={disabled}
          className={clsx(
            'flex size-8 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
            ready
              ? 'bg-foreground text-background hover:bg-foreground/85'
              : 'bg-foreground/10 text-muted-foreground',
          )}
        >
          <PaperAirplaneIcon className="size-4" />
        </button>
      </div>
    </form>
  )
}

const PILL_CLASS =
  'bg-foreground text-background fixed right-6 bottom-6 z-30 inline-flex h-11 items-center gap-2.5 rounded-full pr-[18px] pl-3.5 text-[13.5px] font-medium shadow-[0_8px_24px_-6px_rgba(19,19,17,0.35)] transition-[transform,opacity] duration-150 ease-out lg:hidden'

/**
 * The chat's chrome: the composer card under the score rail (title, one
 * line on scope, the question line), the pill that stands in for it on
 * narrow screens, and the sheet — header strip with the title, the
 * scrolling body, and whatever sits under it (the composer, an error).
 * PaperChat and PaperChatSkeleton both fill it. The sheet stays mounted
 * (translated off-screen) so the thread keeps its scroll position between
 * opens.
 */
export function PaperChatFrame({
  state = 'loaded',
  open = false,
  onOpen,
  onClose,
  label,
  title,
  subtitle,
  hint,
  composer,
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
  /** The one line under the card's title saying what the answers draw on. */
  hint: ReactNode
  /** The rail's question line. */
  composer: ReactNode
  body: ReactNode
  footer: ReactNode
}) {
  return (
    <>
      {/*
        `inert` while the sheet is open: the browser blurs the card, keeps
        Tab out of it and drops it from the accessibility tree, where
        aria-hidden alone would hide a subtree that still holds focus for the
        260ms before the sheet's composer takes it. mt-3 is the gap to the
        score card above; the rail wrapper carries no space-y, which would
        also margin the fixed pill and sheet rendered after this card.
      */}
      <Card
        flush
        data-shape="paper-chat-composer"
        data-state={state}
        inert={open}
        className={clsx(
          'mt-3 overflow-hidden transition-opacity duration-150 ease-out',
          open && 'opacity-55',
        )}
      >
        <div
          data-row="title"
          className="flex items-center gap-2 px-4 pt-3 font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase"
        >
          <ChatBubbleLeftRightIcon aria-hidden="true" className="size-3.5 shrink-0 text-accent" />
          {title}
        </div>
        <p data-row="hint" className="px-4 pt-1.5 pb-2.5 text-xs text-muted-foreground">
          {hint}
        </p>
        {composer}
      </Card>

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
        inert={!open}
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
              <ChatBubbleLeftRightIcon
                aria-hidden="true"
                className="size-3.5 shrink-0 text-accent"
              />
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

/** Before the record arrives: the composer card with its rows boned, the pill, and the sheet closed. */
export function PaperChatSkeleton({ label, title }: { label: string; title: string }) {
  const composer = (
    <div className="border-t border-line-soft">
      <div className="flex items-center gap-2 p-1.5 pl-4">
        <span className="min-w-0 flex-1 text-sm max-sm:text-base">
          <Bone.Text widths={['20ch']} />
        </span>
        <Bone.Block className="size-8" round />
      </div>
    </div>
  )
  return (
    <PaperChatFrame
      state="skeleton"
      label={label}
      title={title}
      hint={<Bone.Text widths={['26ch']} />}
      composer={composer}
      body={
        <p className="text-sm leading-relaxed text-muted-foreground">
          <Bone.Text lines={2} widths={['92%', '48%']} />
        </p>
      }
      footer={composer}
    />
  )
}

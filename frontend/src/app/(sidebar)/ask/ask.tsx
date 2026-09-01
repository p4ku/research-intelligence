'use client'

import type { ChatSession, ChatSessionDetail } from '@/lib/bff/chat/schema'
import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import { useChatStream } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { MagnifyingGlassIcon, PaperAirplaneIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { motion, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { HistoryList, HistoryRail } from './history-rail'
import { PaperPalette } from './paper-palette'
import { AskedHeading, LiveAnswer, SettledAnswer } from './scanner-turn'
import { ScopeToggle } from './scope-toggle'
import {
  shortTitle,
  timeOf,
  type AnswerTurn,
  type AskScope,
  type PaletteEntry,
  type Turn,
} from './types'

const nowTime = () => timeOf(new Date().toISOString())

export function Ask({
  workspaceId,
  entries,
  initialSessions,
  initialPaperId,
  initialSessionId,
}: {
  workspaceId: string
  entries: PaletteEntry[]
  initialSessions: ChatSession[]
  initialPaperId?: string
  initialSessionId?: string
}) {
  const t = useT()
  const initialTarget = initialPaperId
    ? (entries.find((e) => e.id === initialPaperId) ?? null)
    : null

  // The target: what the next question is asked of. null = the whole corpus.
  const [target, setTarget] = useState<PaletteEntry | null>(initialTarget)
  const [turns, setTurns] = useState<Turn[]>([])
  const [sessions, setSessions] = useState<ChatSession[]>(initialSessions)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [openingId, setOpeningId] = useState<string | null>(null)

  // The question the in-flight answer belongs to; null once settled. The ref
  // mirrors it for the stream's finish callback.
  const [liveQuestion, setLiveQuestionState] = useState<string | null>(null)
  const liveQuestionRef = useRef<string | null>(null)
  const setLiveQuestion = (q: string | null) => {
    liveQuestionRef.current = q
    setLiveQuestionState(q)
  }

  const reduceMotion = useReducedMotion()
  const inputRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const mounted = useRef(false)

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true
      return
    }
    if (turns.length === 0) return
    endRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'end' })
  }, [turns.length, reduceMotion])

  // Instant scroll used while an answer streams — smooth scrolling stutters
  // when retriggered every few frames.
  const scrollToEnd = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
  }, [])

  const refreshSessions = useCallback(async () => {
    try {
      const page = await bffFetch<Page<ChatSession>>(
        `/bff/chat/sessions?workspace_id=${workspaceId}&page_size=100`,
      )
      setSessions(page.results)
    } catch {
      // The rail keeps its last known state; the transcript is unaffected.
    }
  }, [workspaceId])

  // Settle the finished stream into the transcript. Runs from the stream
  // loop (not a render effect); ignored when the conversation was cleared
  // mid-flight.
  const {
    state: live,
    send,
    reset,
  } = useChatStream((final) => {
    if (liveQuestionRef.current === null) return
    const answer: AnswerTurn = {
      kind: 'answer',
      text: final.text,
      citations: final.citations,
      visualCitations: final.visualCitations,
      factCheck: final.factCheck,
      usage: final.usage,
      error:
        final.status === 'error'
          ? (final.error?.detail ?? final.error?.title ?? t('The answer failed.'))
          : null,
    }
    setTurns((prev) => [...prev, answer])
    setLiveQuestion(null)
    if (final.sessionId) setActiveSessionId(final.sessionId)
    void refreshSessions()
  })

  async function openThread(session: ChatSession) {
    if (session.id === activeSessionId || openingId) return
    setOpeningId(session.id)
    try {
      const detail = await bffFetch<ChatSessionDetail>(`/bff/chat/sessions/${session.id}`)
      const scope: AskScope = { paper_id: detail.paper_id, title: detail.paper_title }
      const loaded: Turn[] = detail.turns.flatMap((turn): Turn[] => [
        { kind: 'question', text: turn.question, askedAt: timeOf(turn.created_at), scope },
        {
          kind: 'answer',
          text: turn.answer ?? '',
          citations: [],
          visualCitations: turn.visual_citations,
          factCheck: turn.fact_check,
          usage: turn.usage,
          error: turn.status === 'failed' ? (turn.error ?? t('The answer failed.')) : null,
        },
      ])
      setActiveSessionId(detail.id)
      setTurns(loaded)
      setTarget(detail.paper_id ? (entries.find((e) => e.id === detail.paper_id) ?? null) : null)
      setLiveQuestion(null)
      reset()
      setInput('')
      window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
    } catch {
      // Leave the console as it was.
    } finally {
      setOpeningId(null)
    }
  }

  // Deep link: ?session=<id> opens that thread once.
  const openedInitial = useRef(false)
  useEffect(() => {
    if (openedInitial.current || !initialSessionId) return
    openedInitial.current = true
    const session = sessions.find((s) => s.id === initialSessionId)
    if (session) void openThread(session)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId, sessions])

  function newThread() {
    setActiveSessionId(null)
    setTurns([])
    setTarget(null)
    setLiveQuestion(null)
    reset()
    setInput('')
  }

  async function deleteThread(session: ChatSession) {
    try {
      await bffFetch<void>(`/bff/chat/sessions/${session.id}`, { method: 'DELETE' })
      setSessions((prev) => prev.filter((s) => s.id !== session.id))
      if (session.id === activeSessionId) newThread()
    } catch {
      // Row stays; nothing else to do.
    }
  }

  function switchTarget(entry: PaletteEntry | null) {
    if ((entry?.id ?? null) === (target?.id ?? null)) {
      inputRef.current?.focus()
      return
    }
    setTarget(entry)
    // A target switch starts a fresh session on the next question (sessions
    // are bound to one scope) — mid-conversation it leaves one quiet line.
    setActiveSessionId(null)
    if (turns.length > 0) {
      setTurns((prev) => [
        ...prev,
        { kind: 'target', scope: { paper_id: entry?.id ?? null, title: entry?.title ?? null } },
      ])
    }
    inputRef.current?.focus()
  }

  function ask(q: string) {
    if (liveQuestion !== null) return // one question at a time
    const scope: AskScope = { paper_id: target?.id ?? null, title: target?.title ?? null }
    setTurns((prev) => [...prev, { kind: 'question', text: q, askedAt: nowTime(), scope }])
    setLiveQuestion(q)
    setInput('')
    void send({
      question: q,
      paper_id: target?.id,
      workspace_id: target ? undefined : workspaceId,
      session_id: activeSessionId ?? undefined,
      deep_thinking: false,
    })
  }

  const hasConversation = turns.length > 0 || liveQuestion !== null

  return (
    <>
      <div className="grid items-start gap-6 lg:grid-cols-3">
        {/* Console: the ask field sits at the top; the conversation follows below it. */}
        <section
          aria-label={t('Ask console')}
          className="border-line bg-surface isolate flex min-w-0 flex-col rounded-sm border shadow-xs lg:col-span-2"
        >
          <div className="border-line-soft flex items-center gap-3 border-b px-4 py-2.5">
            <span className="text-foreground font-mono text-[11px] font-medium tracking-[0.18em] uppercase">
              Ask
            </span>
            {/* Scope lives in the header strip — set the aim before typing. */}
            <div className="ml-auto min-w-0">
              <ScopeToggle
                target={target}
                onPick={() => setPaletteOpen(true)}
                onCorpus={() => switchTarget(null)}
              />
            </div>
          </div>

          <div className="p-4 sm:p-6">
            <Composer
              target={target}
              value={input}
              onChange={setInput}
              onSubmit={ask}
              inputRef={inputRef}
              busy={liveQuestion !== null}
            />

            {hasConversation && (
              <div className="mt-8 space-y-5">
                {turns.map((turn, i) => (
                  <motion.div
                    key={i}
                    initial={false}
                    animate={{ opacity: 1, y: 0 }}
                    className={clsx(turn.kind === 'question' && i > 0 && 'pt-2')}
                  >
                    {turn.kind === 'target' ? (
                      <TargetLine scope={turn.scope} />
                    ) : turn.kind === 'question' ? (
                      <AskedHeading turn={turn} divider={i > 0} />
                    ) : (
                      <SettledAnswer
                        turn={turn}
                        anchor={`vc-${i}`}
                        onDigIn={(id) => switchTarget(entries.find((e) => e.id === id) ?? null)}
                      />
                    )}
                  </motion.div>
                ))}
                {liveQuestion !== null && (
                  <LiveAnswer
                    state={live}
                    scopeTitle={target ? shortTitle(target.title) : null}
                    corpusCount={entries.length}
                    onGrow={scrollToEnd}
                  />
                )}
                <div ref={endRef} aria-hidden="true" className="scroll-mb-6" />
              </div>
            )}
          </div>
        </section>

        {/* History rail: always to the right. */}
        <aside aria-label={t('Conversation history')} className="max-lg:hidden lg:col-span-1">
          <HistoryRail
            threads={sessions}
            activeId={activeSessionId}
            onOpen={openThread}
            onNew={newThread}
            onDelete={deleteThread}
          />
        </aside>

        <details className="border-line bg-surface rounded-sm border px-4 py-3 lg:hidden">
          <summary className="text-foreground cursor-default text-xs font-semibold tracking-[0.18em] uppercase">
            {t('History')}{' '}
            <span className="text-muted-foreground font-mono font-normal normal-case tabular-nums">
              · {fmt(t('{n} asked'), { n: sessions.length })}
            </span>
          </summary>
          <div className="mt-3">
            <HistoryList
              threads={sessions}
              activeId={activeSessionId}
              onOpen={openThread}
              onDelete={deleteThread}
            />
          </div>
        </details>
      </div>

      <PaperPalette
        open={paletteOpen}
        entries={entries}
        currentPaperId={target?.id}
        onClose={() => setPaletteOpen(false)}
        onSelect={(entry) => switchTarget(entry)}
      />
    </>
  )
}

/** A bare target change: one quiet centered line, no rules, no card. */
function TargetLine({ scope }: { scope: { paper_id: string | null; title: string | null } }) {
  const t = useT()
  return (
    <p
      role="separator"
      className="text-muted-foreground text-center font-mono text-[11px] tracking-[0.05em]"
    >
      {t('Target')} →{' '}
      {scope.title
        ? fmt(t('{title} · full text'), { title: shortTitle(scope.title) })
        : t('All papers')}
    </p>
  )
}

/** The question field — styled like the Papers & Briefings search. */
function Composer({
  target,
  value,
  onChange,
  onSubmit,
  inputRef,
  busy,
}: {
  target: PaletteEntry | null
  value: string
  onChange: (v: string) => void
  onSubmit: (q: string) => void
  inputRef: React.RefObject<HTMLInputElement | null>
  busy: boolean
}) {
  const t = useT()
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (value.trim() && !busy) onSubmit(value.trim())
      }}
      className="group border-line bg-surface focus-within:border-accent/60 focus-within:ring-accent/15 relative flex items-center gap-3 rounded-md border px-4 py-3 transition focus-within:ring-4"
    >
      <MagnifyingGlassIcon
        className={clsx(
          'size-5 shrink-0 transition-colors',
          target ? 'text-accent' : 'group-focus-within:text-accent text-zinc-400',
        )}
      />
      <input
        ref={inputRef}
        name="question"
        aria-label={t('Ask a question')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          target
            ? fmt(t('Ask about {title}…'), { title: shortTitle(target.title) })
            : t('Ask across all papers…')
        }
        className="text-foreground placeholder:text-muted-foreground min-w-0 flex-1 bg-transparent text-base focus:outline-none max-sm:text-base"
      />
      <button
        type="submit"
        aria-label={t('Send')}
        disabled={busy}
        className={clsx(
          'focus-visible:outline-accent relative flex size-8 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2',
          value.trim() && !busy
            ? 'bg-foreground text-background hover:bg-foreground/85'
            : 'bg-foreground/10 text-muted-foreground',
        )}
      >
        <span
          className="absolute top-1/2 left-1/2 size-[max(100%,3rem)] -translate-1/2 pointer-fine:hidden"
          aria-hidden="true"
        />
        <PaperAirplaneIcon className="size-4" />
      </button>
    </form>
  )
}

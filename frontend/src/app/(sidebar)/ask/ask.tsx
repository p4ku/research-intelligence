'use client'

import type { ChatSession, ChatSessionDetail } from '@/lib/bff/chat/schema'
import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import { useChatStream, type ChatStreamState } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import {
  ArrowDownIcon,
  ChevronUpDownIcon,
  PaperAirplaneIcon,
  StopIcon,
  XMarkIcon,
} from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { HistoryList, HistoryRail } from './history-rail'
import { MiniScore, PaperPicker, pickable, scoreColor } from './paper-picker'
import { AskedHeading, FollowUps, LiveAnswer, SettledAnswer } from './scanner-turn'
import {
  shortTitle,
  timeOf,
  type AnswerTurn,
  type AskScope,
  type PaletteEntry,
  type QuestionTurn,
  type Turn,
} from './types'
import { useTranscriptScroll } from './use-transcript-scroll'

const nowTime = () => timeOf(new Date().toISOString())
const EASE_OUT = [0.23, 1, 0.32, 1] as const
const EASE_IN_OUT = [0.77, 0, 0.175, 1] as const
const FIELD_MAX_PX = 176
const RAISED =
  'shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)] dark:shadow-none'

/** The transcript as question/answer pairs, with target changes between. */
type Group =
  | { kind: 'target'; key: number; scope: AskScope }
  | { kind: 'qa'; key: number; question: QuestionTurn; answer: AnswerTurn | null }

function groupTurns(turns: Turn[]): Group[] {
  const groups: Group[] = []
  turns.forEach((turn, i) => {
    if (turn.kind === 'target') groups.push({ kind: 'target', key: i, scope: turn.scope })
    else if (turn.kind === 'question')
      groups.push({ kind: 'qa', key: i, question: turn, answer: null })
    else {
      const last = groups[groups.length - 1]
      if (last?.kind === 'qa' && !last.answer) last.answer = turn
    }
  })
  return groups
}

function autogrow(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, FIELD_MAX_PX)}px`
}

/**
 * The Ask console. Conversations are scoped to one paper: until a paper is
 * chosen the composer is the picker; once chosen, the paper rides in the
 * composer as a chip and questions go to its full text. The composer starts
 * in the upper third of the empty console and docks at the bottom on the
 * first question; the transcript above it anchors each new question to the
 * top and follows the streamed answer.
 */
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
  const reduceMotion = useReducedMotion() ?? false
  const initialTarget = initialPaperId
    ? (entries.find((e) => e.id === initialPaperId) ?? null)
    : null

  const [target, setTarget] = useState<PaletteEntry | null>(initialTarget)
  const [turns, setTurns] = useState<Turn[]>([])
  const [sessions, setSessions] = useState<ChatSession[]>(initialSessions)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [pickQuery, setPickQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const [openingId, setOpeningId] = useState<string | null>(null)
  // Bumps per question so the anchor effect fires even for a repeated question.
  const [askSeq, setAskSeq] = useState(0)

  // The question the in-flight answer belongs to; null once settled. The ref
  // mirrors it for callbacks that run outside render.
  const [liveQuestion, setLiveQuestionState] = useState<string | null>(null)
  const liveQuestionRef = useRef<string | null>(null)
  const setLiveQuestion = (q: string | null) => {
    liveQuestionRef.current = q
    setLiveQuestionState(q)
  }
  // The paper the current conversation is bound to (sessions are one-scope).
  const scopeRef = useRef<string | null>(initialTarget?.id ?? null)

  const fieldRef = useRef<HTMLTextAreaElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const dockRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const busy = liveQuestion !== null
  const mode: 'pick' | 'ask' = target ? 'ask' : 'pick'
  const hasConversation = turns.length > 0
  const groups = groupTurns(turns)

  const {
    ref: transcriptRef,
    jump,
    onScroll,
    anchorTurn,
    follow,
    jumpToLatest,
    setBusy,
  } = useTranscriptScroll(reduceMotion)
  useEffect(() => setBusy(busy), [busy, setBusy])

  // The jump button sits just above the dock, whatever height the field has.
  useEffect(() => {
    const dock = dockRef.current
    const body = bodyRef.current
    if (!dock || !body) return
    const measure = () => body.style.setProperty('--dock-h', `${dock.offsetHeight}px`)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(dock)
    return () => ro.disconnect()
  }, [])

  // The field shrinks back when its value is cleared from code.
  useEffect(() => {
    if (fieldRef.current) autogrow(fieldRef.current)
  }, [input, pickQuery, mode])

  const focusField = () => fieldRef.current?.focus()

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

  /* ------------------------------ Settling ------------------------------ */

  // A stream settles into the transcript once two things are true: the
  // stream has finished (finalRef) and the reveal has shown every word
  // (revealedRef). Either can come first.
  const finalRef = useRef<ChatStreamState | null>(null)
  const revealedRef = useRef(false)
  const stoppedRef = useRef(false)

  const commit = useCallback(
    (final: ChatStreamState) => {
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
        arrived: true,
        stopped: stoppedRef.current,
      }
      stoppedRef.current = false
      setTurns((prev) => [...prev, answer])
      setLiveQuestion(null)
      if (final.sessionId) setActiveSessionId(final.sessionId)
      void refreshSessions()
      focusField()
    },
    [refreshSessions, t],
  )

  const trySettle = useCallback(() => {
    const final = finalRef.current
    if (!final || !revealedRef.current || liveQuestionRef.current === null) return
    finalRef.current = null
    revealedRef.current = false
    // Let the last words finish unveiling before the tail arrives.
    const delay = reduceMotion || final.status === 'error' ? 0 : 600
    window.setTimeout(() => commit(final), delay)
  }, [commit, reduceMotion])

  const {
    state: live,
    send,
    abort,
    reset,
  } = useChatStream((final) => {
    if (liveQuestionRef.current === null) return
    finalRef.current = final
    trySettle()
  })

  const onRevealed = useCallback(() => {
    revealedRef.current = true
    trySettle()
  }, [trySettle])

  const clearInFlight = () => {
    finalRef.current = null
    revealedRef.current = false
    stoppedRef.current = false
    setLiveQuestion(null)
    reset()
  }

  /* ------------------------------ Sessions ------------------------------ */

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
      clearInFlight()
      setActiveSessionId(detail.id)
      setTurns(loaded)
      const paper = detail.paper_id ? (entries.find((e) => e.id === detail.paper_id) ?? null) : null
      setTarget(paper)
      scopeRef.current = detail.paper_id
      setInput('')
      setPickQuery('')
      setCursor(0)
      transcriptRef.current?.scrollTo({ top: 0 })
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
    clearInFlight()
    setActiveSessionId(null)
    setTurns([])
    setTarget(null)
    scopeRef.current = null
    setInput('')
    setPickQuery('')
    setCursor(0)
    focusField()
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

  /* ------------------------------- Target ------------------------------- */

  function pick(entry: PaletteEntry) {
    setTarget(entry)
    setPickQuery('')
    setCursor(0)
    // A different paper mid-conversation starts a fresh session on the next
    // question, leaving one quiet line in the transcript.
    if (turns.length > 0 && scopeRef.current !== entry.id) {
      setActiveSessionId(null)
      setTurns((prev) => [
        ...prev,
        { kind: 'target', scope: { paper_id: entry.id, title: entry.title } },
      ])
    }
    focusField()
  }

  function unpick() {
    if (busy) return
    setTarget(null)
    setPickQuery('')
    setCursor(0)
    focusField()
  }

  /* ------------------------------- Asking ------------------------------- */

  function ask(q: string) {
    if (busy || !target) return
    const scope: AskScope = { paper_id: target.id, title: target.title }
    scopeRef.current = target.id
    setTurns((prev) => [...prev, { kind: 'question', text: q, askedAt: nowTime(), scope }])
    setLiveQuestion(q)
    setAskSeq((n) => n + 1)
    setInput('')
    void send({
      question: q,
      paper_id: target.id,
      session_id: activeSessionId ?? undefined,
      deep_thinking: false,
    })
  }

  // A new question rises to the top of the transcript.
  useLayoutEffect(() => {
    if (askSeq === 0) return
    const el = listRef.current?.querySelector<HTMLElement>('article[data-live]')
    if (el) anchorTurn(el)
  }, [askSeq, anchorTurn])

  function stop() {
    if (!busy) return
    stoppedRef.current = true
    const connecting = live.status === 'connecting'
    abort()
    // Before the first byte the hook has nothing to settle; file the empty turn ourselves.
    if (connecting) {
      revealedRef.current = true
      finalRef.current = { ...live, status: 'done' }
      trySettle()
    }
  }

  function submit() {
    if (mode === 'pick') {
      focusField()
      return
    }
    const q = input.trim()
    if (!q || busy) return
    ask(q)
  }

  function onFieldChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    autogrow(e.target)
    if (mode === 'pick') {
      setPickQuery(value)
      setCursor(0)
      return
    }
    // @ on its own is the way back to the picker.
    if (value.trim() === '@') {
      setInput('')
      unpick()
      return
    }
    setInput(value)
  }

  function onFieldKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (mode === 'pick') {
      const rows = pickable(entries, pickQuery)
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor((c) => Math.min(c + 1, rows.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor((c) => Math.max(c - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const row = rows[cursor]
        if (row) pick(row)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        setPickQuery('')
        setCursor(0)
      }
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const lastGroup = groups[groups.length - 1]
  const sendLive = busy || (mode === 'ask' && input.trim() !== '')

  return (
    <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(17rem,1fr)] lg:grid-rows-1">
      {/* Console: transcript above, the composer docked below. */}
      <section
        aria-label={t('Ask console')}
        className={clsx(
          'border-line-strong bg-surface relative isolate flex min-h-0 min-w-0 flex-col rounded-sm border',
          RAISED,
        )}
      >
        <div className="border-line-soft flex shrink-0 items-center gap-3 border-b px-4 py-2.5">
          <span className="text-foreground font-mono text-[11px] font-medium tracking-[0.18em] uppercase">
            Ask
          </span>
          <div className="ml-auto flex min-w-0 items-center">
            {target ? (
              <button
                type="button"
                onClick={unpick}
                disabled={busy}
                title={t('Change paper')}
                className="hover:bg-foreground/5 flex max-w-80 min-w-0 items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-left transition-colors duration-150 ease-out disabled:cursor-default disabled:hover:bg-transparent"
              >
                <MiniScore score={target.signal_score} />
                <span className="text-foreground truncate text-[11px] font-medium">
                  {shortTitle(target.title)}
                </span>
                <ChevronUpDownIcon className="text-muted-foreground size-3 shrink-0" />
              </button>
            ) : (
              <span className="text-muted-foreground font-mono text-[10px] tracking-[0.07em] uppercase">
                {t('No paper yet')}
              </span>
            )}
          </div>
        </div>

        <div
          ref={bodyRef}
          className={clsx(
            'relative flex min-h-0 flex-1 flex-col',
            !hasConversation && 'pt-[clamp(2rem,10vh,7rem)]',
          )}
        >
          {hasConversation && (
            <div
              ref={transcriptRef}
              onScroll={onScroll}
              className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pt-2 lg:px-8"
            >
              <div ref={listRef} className="mx-auto max-w-[800px]">
                {groups.map((g) =>
                  g.kind === 'target' ? (
                    <TargetLine key={g.key} scope={g.scope} />
                  ) : (
                    <article
                      key={g.key}
                      data-live={!g.answer && busy ? '' : undefined}
                      className={clsx(
                        'border-line-soft border-t pt-[18px] pb-2 first:border-t-0 last:min-h-(--turn-min)',
                        !g.answer && busy && 'animate-rise-in motion-reduce:animate-none',
                      )}
                    >
                      <AskedHeading turn={g.question} />
                      {g.answer ? (
                        <>
                          <SettledAnswer turn={g.answer} anchor={`vc-${g.key}`} />
                          {g === lastGroup && !busy && !g.answer.error && target && (
                            <FollowUps exclude={g.question.text} onAsk={ask} />
                          )}
                        </>
                      ) : busy ? (
                        <LiveAnswer
                          key={askSeq}
                          state={live}
                          scopeTitle={target ? shortTitle(target.title) : null}
                          onGrow={follow}
                          onRevealed={onRevealed}
                        />
                      ) : null}
                    </article>
                  ),
                )}
              </div>
            </div>
          )}

          <AnimatePresence>
            {jump && (
              <motion.button
                key="jump"
                type="button"
                onClick={jumpToLatest}
                initial={{ opacity: 0, y: 6, scale: 0.94 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 6, scale: 0.94 }}
                transition={{ duration: reduceMotion ? 0 : 0.2, ease: EASE_OUT }}
                className={clsx(
                  'border-line-strong bg-surface text-foreground absolute bottom-[calc(var(--dock-h,6rem)+0.75rem)] left-1/2 z-[6] flex -translate-x-1/2 items-center gap-1.5 rounded-sm border py-1.5 pr-2.5 pl-2 text-xs font-medium',
                  RAISED,
                )}
              >
                <ArrowDownIcon className="size-3" />
                {t('Jump to latest')}
              </motion.button>
            )}
          </AnimatePresence>

          <AnimatePresence initial={false} mode="popLayout">
            {!hasConversation && (
              <motion.div
                key="greeting"
                exit={{ opacity: 0 }}
                transition={{ duration: reduceMotion ? 0 : 0.15 }}
                className="mx-auto mb-[18px] w-[min(100%-3rem,800px)] shrink-0"
              >
                <p className="text-muted-foreground font-mono text-[10px] font-medium tracking-[0.18em] uppercase">
                  {t('One paper at a time')}
                </p>
                <p className="text-foreground mt-1.5 text-[15px] text-balance">
                  {t('Every answer is read from a single paper’s full text.')}{' '}
                  <span className="text-muted-foreground">
                    {t('Choose the paper, then ask it anything.')}
                  </span>
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* The dock: composer + picker. Same element before and after the first question — it travels. */}
          <motion.div
            ref={dockRef}
            layout="position"
            transition={{ layout: { duration: reduceMotion ? 0 : 0.42, ease: EASE_IN_OUT } }}
            className={clsx(
              'relative z-[4] mx-auto w-[min(100%-3rem,800px)] shrink-0 pb-5',
              hasConversation &&
                'before:to-surface pt-3 before:pointer-events-none before:absolute before:-top-7 before:-right-6 before:-left-6 before:h-10 before:bg-gradient-to-b before:from-transparent',
            )}
          >
            <form
              onSubmit={(e) => {
                e.preventDefault()
                submit()
              }}
              className="border-line bg-surface focus-within:border-accent/60 focus-within:ring-accent/15 relative flex flex-col rounded-sm border transition focus-within:ring-4"
            >
              <textarea
                ref={fieldRef}
                name="question"
                rows={1}
                value={mode === 'pick' ? pickQuery : input}
                onChange={onFieldChange}
                onKeyDown={onFieldKeyDown}
                role={mode === 'pick' ? 'combobox' : undefined}
                aria-expanded={mode === 'pick' ? true : undefined}
                aria-controls={mode === 'pick' ? 'paper-picker' : undefined}
                aria-autocomplete={mode === 'pick' ? 'list' : undefined}
                aria-label={mode === 'pick' ? t('Find a paper') : t('Ask a question')}
                placeholder={
                  mode === 'pick'
                    ? t('Which paper? Type a title, author, or source…')
                    : t('Ask about this paper…')
                }
                autoComplete="off"
                spellCheck={false}
                className="text-foreground placeholder:text-muted-foreground block max-h-44 w-full resize-none bg-transparent px-4 pt-3.5 pb-1.5 text-[15px] leading-relaxed focus:outline-none"
              />
              <div className="flex min-h-10 items-center gap-2 py-1.5 pr-2 pb-2 pl-3">
                {target && (
                  <motion.span
                    initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.18, ease: EASE_OUT }}
                    className="bg-foreground/5 flex max-w-[70%] items-center gap-1.5 rounded-sm py-[3px] pr-1 pl-2"
                  >
                    <span
                      aria-hidden="true"
                      className="size-1.5 shrink-0 rounded-full"
                      style={{ backgroundColor: scoreColor(target.signal_score) }}
                    />
                    <span className="text-foreground truncate text-xs font-medium">
                      {shortTitle(target.title)}
                    </span>
                    <button
                      type="button"
                      onClick={unpick}
                      disabled={busy}
                      aria-label={t('Choose a different paper')}
                      className="text-muted-foreground hover:bg-foreground/10 hover:text-foreground grid size-[18px] shrink-0 place-items-center rounded-full transition-colors duration-100 ease-out disabled:opacity-50"
                    >
                      <XMarkIcon className="size-3" />
                    </button>
                  </motion.span>
                )}
                <span className="flex-1" />
                <button
                  type={busy ? 'button' : 'submit'}
                  onClick={busy ? stop : undefined}
                  aria-label={busy ? t('Stop') : t('Send')}
                  className={clsx(
                    'focus-visible:outline-accent relative flex size-8 shrink-0 items-center justify-center rounded-full transition-[background-color,color,transform] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 active:scale-[0.94]',
                    sendLive
                      ? 'bg-foreground text-background hover:bg-foreground/85'
                      : 'bg-foreground/10 text-muted-foreground',
                  )}
                >
                  {busy ? (
                    <StopIcon className="size-3.5" />
                  ) : (
                    <PaperAirplaneIcon className="size-4" />
                  )}
                </button>
              </div>
            </form>

            {mode === 'pick' && (
              <PaperPicker
                entries={entries}
                query={pickQuery}
                cursor={cursor}
                placement={hasConversation ? 'above' : 'below'}
                onCursor={setCursor}
                onPick={pick}
              />
            )}
          </motion.div>
        </div>
      </section>

      {/* History rail: always to the right. */}
      <aside
        aria-label={t('Conversation history')}
        className="min-h-0 overflow-y-auto pb-6 max-lg:hidden"
      >
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
        <div className="mt-3 max-h-72 overflow-y-auto">
          <HistoryList
            threads={sessions}
            activeId={activeSessionId}
            onOpen={openThread}
            onDelete={deleteThread}
          />
        </div>
      </details>
    </div>
  )
}

/** A bare target change: one quiet centered line, no rules, no card. */
function TargetLine({ scope }: { scope: AskScope }) {
  const t = useT()
  return (
    <p
      role="separator"
      className="text-muted-foreground pt-3.5 pb-1 text-center font-mono text-[11px] tracking-[0.05em]"
    >
      {t('Target')} →{' '}
      {scope.title
        ? fmt(t('{title} · full text'), { title: shortTitle(scope.title) })
        : t('All papers')}
    </p>
  )
}

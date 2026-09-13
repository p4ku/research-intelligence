'use client'

import { ErrorNote } from '@/components/scanner-ui'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Spinner } from '@/components/ui/spinner'
import type { ChatSession, ChatSessionDetail } from '@/lib/bff/chat/schema'
import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import { problemMessage } from '@/lib/bff/problem-copy'
import { useChatStream, type ChatStreamState } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import {
  ArrowDownIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  StopIcon,
  XMarkIcon,
} from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  AskCanvas,
  BODY_CLASS,
  ComposerFrame,
  DOCK_WRAP,
  EMPTY_BODY,
  FIELD_CLASS,
  GREETING_WRAP,
  Greeting,
  ICON_BUTTON,
  PanelRightIcon,
  RAISED,
  TopBar,
} from './console-frame'
import { HistorySidecar } from './history-sidecar'
import { PaperPicker, pickable, scoreColor } from './paper-picker'
import { AskedBubble, FollowUps, LiveAnswer, SettledAnswer } from './scanner-turn'
import { ToolMenu } from './tool-menu'
import {
  shortTitle,
  timeOf,
  type AnswerTurn,
  type AskScope,
  type PaletteEntry,
  type QuestionTurn,
  type ScopeTarget,
  type Turn,
} from './types'
import { usePalette } from './use-palette'
import { useTranscriptScroll } from './use-transcript-scroll'

const nowTime = () => timeOf(new Date().toISOString())
const EASE_OUT = [0.23, 1, 0.32, 1] as const
const EASE_IN_OUT = [0.77, 0, 0.175, 1] as const
const FIELD_MAX_PX = 176

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
  const full = el.scrollHeight
  el.style.height = `${Math.min(full, FIELD_MAX_PX)}px`
  // scrollHeight is an integer while the line box is not (15px × 1.625 plus
  // padding), so a box sized to it is a fraction short of its content and the
  // browser draws a scrollbar. Only a field at its cap has anything to scroll.
  el.style.overflowY = full > FIELD_MAX_PX ? 'auto' : 'hidden'
}

/**
 * The Ask canvas — a general chat surface, and the home for every agentic
 * tool the assistant grows. Today the one tool that is wired is "attach a
 * paper", so conversations are still scoped to one paper's full text: ask
 * with nothing attached and the picker opens holding your question, then
 * sends it the moment you choose. The paper then rides in the composer as a
 * removable chip. The composer starts centred on the empty canvas and docks
 * at the bottom on the first question; the transcript above it anchors each
 * new question to the top and follows the streamed answer. Past conversations
 * live in a sidecar that slides over the right gutter, hidden by default.
 *
 * The console mounts with nothing fetched. The corpus behind the picker and
 * the history behind the sidecar both arrive after paint — each surface
 * shows its own bones if the reader reaches it first — so the composer is
 * ready the moment the page is.
 */
export function Ask({
  initialTarget = null,
  initialSessionId,
  initialQuestion,
}: {
  /** A `?paper=` deep link, resolved by the page to the chip's few fields. */
  initialTarget?: ScopeTarget | null
  initialSessionId?: string
  /** Seeds the composer (Home's search handed over); the reader still presses Send. */
  initialQuestion?: string
}) {
  const t = useT()
  const reduceMotion = useReducedMotion() ?? false
  const [target, setTarget] = useState<ScopeTarget | null>(initialTarget)
  const [turns, setTurns] = useState<Turn[]>([])
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [historyStatus, setHistoryStatus] = useState<'loading' | 'ready' | 'stale'>('loading')
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [input, setInput] = useState(initialQuestion ?? '')
  const [pickQuery, setPickQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  // The composer becomes the paper picker on demand, not by default.
  const [picking, setPicking] = useState(false)
  // The rows for what is being typed into the picker; the empty palette otherwise.
  const {
    entries,
    matched: paletteMatched,
    total: paletteTotal,
    status: paletteStatus,
    retry: retryPalette,
  } = usePalette(picking ? pickQuery : '')
  // A question asked before a paper was attached; it sends itself once one is.
  const [held, setHeld] = useState<string | null>(null)
  const [sidecarOpen, setSidecarOpen] = useState(false)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)
  // The delete flow: a row only nominates; the AlertDialog confirms.
  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  // The trash button that opened the dialog — focus returns to it on close
  // (a controlled dialog with no Trigger would otherwise focus <body>).
  const deleteTriggerRef = useRef<HTMLElement | null>(null)
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
  const mode: 'pick' | 'ask' = picking ? 'pick' : 'ask'
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

  // How far the dock's top sits above the canvas floor. The jump button and
  // the recents panel both stop there, whatever height the field has and
  // wherever the dock is — centred on an empty canvas, docked once a
  // conversation exists. `offsetTop` is the layout position, so this reads the
  // settled geometry even mid-FLIP, when a rect would still carry the
  // travelling transform. The variable goes on the canvas rather than the body
  // because the panel is the body's sibling, not its descendant.
  //
  // Re-fitting the field here is what keeps a wrapped question readable when
  // the window narrows: `autogrow` freezes an inline height, and the dock
  // resizing is the signal that the measure changed. It settles in one extra
  // pass — the re-fit either leaves the height alone or reports it once more.
  useEffect(() => {
    const dock = dockRef.current
    const body = bodyRef.current
    const canvas = body?.parentElement
    if (!dock || !body || !canvas) return
    const measure = () => {
      const floor = canvas.clientHeight - (body.offsetTop + dock.offsetTop)
      canvas.style.setProperty('--dock-top', `${floor}px`)
      if (fieldRef.current) autogrow(fieldRef.current)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(dock)
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [hasConversation])

  // The field shrinks back when its value is cleared from code.
  useEffect(() => {
    if (fieldRef.current) autogrow(fieldRef.current)
  }, [input, pickQuery, mode])

  const focusField = () => fieldRef.current?.focus()

  // `mine` matters: Django lists a whole workspace to its admins and
  // managers, and this rail opens and deletes what it lists — neither may
  // ever land on a colleague's conversation.
  const refreshSessions = useCallback(async () => {
    try {
      const page = await bffFetch<Page<ChatSession>>('/bff/chat/sessions?mine=1&page_size=100')
      setSessions(page.results)
      setHistoryStatus('ready')
    } catch (error) {
      // The rail keeps its last known state — but says so instead of
      // letting a just-finished conversation silently not appear.
      console.error('[ask] session refresh failed:', error)
      setHistoryStatus('stale')
    }
  }, [])

  // The history arrives after paint: the sidecar is closed until asked for,
  // and a `?session=` deep link opens itself once the list is in (below).
  useEffect(() => {
    void refreshSessions()
  }, [refreshSessions])

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
        error: final.status === 'error' ? problemMessage(final.error, t) : null,
        arrived: true,
        stopped: stoppedRef.current,
      }
      stoppedRef.current = false
      setTurns((prev) => [...prev, answer])
      // A failure before the first token restores the question to the composer
      // (never clobbering anything typed since) so it isn't lost to a blip.
      if (answer.error && final.text === '') {
        const q = liveQuestionRef.current
        setInput((cur) => (cur === '' && q ? q : cur))
      }
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
    stop: stopStream,
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
    setRowError(null)
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
          stopped: turn.status === 'aborted',
        },
      ])
      clearInFlight()
      setActiveSessionId(detail.id)
      setTurns(loaded)
      // The thread knows its paper; the corpus row (when it has arrived)
      // adds the signal for the chip's dot.
      const paper: ScopeTarget | null = detail.paper_id
        ? (entries.find((e) => e.id === detail.paper_id) ?? {
            id: detail.paper_id,
            title: detail.paper_title ?? t('Untitled paper'),
            signal_score: null,
          })
        : null
      setTarget(paper)
      scopeRef.current = detail.paper_id
      setInput('')
      setPicking(false)
      setHeld(null)
      setPickQuery('')
      setCursor(0)
      transcriptRef.current?.scrollTo({ top: 0 })
    } catch (error) {
      // The console keeps its state; the row says what happened.
      console.error('[ask] open failed:', error)
      setRowError({ id: session.id, message: t("Couldn't open this conversation. Try again.") })
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
    setPicking(false)
    setHeld(null)
    setPickQuery('')
    setCursor(0)
    focusField()
  }

  function requestDelete(session: ChatSession) {
    deleteTriggerRef.current = document.activeElement as HTMLElement | null
    setDeleteError(null)
    setPendingDelete(session)
  }

  async function confirmDelete() {
    const session = pendingDelete
    if (!session || deleting) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await bffFetch<void>(`/bff/chat/sessions/${session.id}`, { method: 'DELETE' })
      setSessions((prev) => prev.filter((s) => s.id !== session.id))
      if (session.id === activeSessionId) newThread()
      setPendingDelete(null)
      // The row — the outcome's anchor — is gone, so this is the one place
      // a toast is right (see the Toaster note in app/layout.tsx).
      toast(t('Conversation deleted'))
    } catch (error) {
      // The dialog stays open: a failed destructive action is never silent.
      console.error('[ask] delete failed:', error)
      setDeleteError(t("Couldn't delete this conversation. Try again."))
    } finally {
      setDeleting(false)
    }
  }

  /* ------------------------------- Target ------------------------------- */

  function pick(entry: PaletteEntry) {
    setTarget(entry)
    setPicking(false)
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
    // A question that was waiting on a paper goes now — the reader already
    // pressed send once; the picker was the interruption, not a new step.
    if (held) {
      setHeld(null)
      ask(held, entry)
      return
    }
    focusField()
  }

  /** Leave the picker with nothing chosen; a held question returns to the field. */
  function cancelPick() {
    setPicking(false)
    setPickQuery('')
    setCursor(0)
    if (held) {
      setInput((cur) => (cur === '' ? held : cur))
      setHeld(null)
    }
    focusField()
  }

  /** Detach the paper. The next question re-opens the picker holding itself. */
  function unpick() {
    if (busy) return
    setTarget(null)
    focusField()
  }

  /* ------------------------------- Asking ------------------------------- */

  /**
   * `on` lets `pick` send a held question with the paper it just chose:
   * `target` state has not landed yet on that path.
   */
  function ask(q: string, on?: ScopeTarget) {
    const paper = on ?? target
    if (busy || !paper) return
    const scope: AskScope = { paper_id: paper.id, title: paper.title }
    scopeRef.current = paper.id
    setTurns((prev) => [...prev, { kind: 'question', text: q, askedAt: nowTime(), scope }])
    setLiveQuestion(q)
    setAskSeq((n) => n + 1)
    setInput('')
    void send({
      question: q,
      paper_id: paper.id,
      session_id: activeSessionId ?? undefined,
      deep_thinking: false,
    })
  }

  /**
   * Regenerate the transcript's last, failed answer: drop the trailing QA
   * pair and re-ask the same question. Only offered on the last group — a
   * target switch inserts a TargetTurn and retires the affordance, so the
   * question's scope is always the current target and truncation can never
   * eat a good turn below it.
   */
  function retryFrom(key: number) {
    if (busy) return
    const q = turns[key]
    if (q?.kind !== 'question') return
    setTurns((prev) => prev.slice(0, key))
    ask(q.text)
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
    // The hook files what has arrived as a done turn (connecting included:
    // an empty done settles through the reveal handshake like any other).
    stopStream()
  }

  /** Open the picker; `holding` is a question that will send on choosing. */
  function startPick(holding?: string) {
    if (busy) return
    // A picker opened onto a failed corpus load asks again by itself.
    if (paletteStatus === 'error') retryPalette()
    setHeld(holding ?? null)
    setPickQuery('')
    setCursor(0)
    setPicking(true)
    focusField()
  }

  function submit() {
    if (mode === 'pick') {
      const row = pickable(entries, pickQuery)[cursor]
      if (row) pick(row)
      return
    }
    const q = input.trim()
    if (!q || busy) return
    // Nothing attached yet: hold the question and ask which paper it is about.
    if (!target) {
      setInput('')
      startPick(q)
      return
    }
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
    // @ on its own opens the picker.
    if (value.trim() === '@') {
      setInput('')
      startPick()
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
        cancelPick()
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
  const firstQuestion = turns.find((x): x is QuestionTurn => x.kind === 'question')
  // The thread's name: the saved title once there is a session, otherwise the
  // question that opened it — the same thing the sidecar will file it under.
  const threadTitle =
    sessions.find((s) => s.id === activeSessionId)?.title ?? firstQuestion?.text ?? t('New chat')

  // The chrome lives in ./console-frame so the loading skeleton shares it.
  return (
    <>
      <AskCanvas
        label={t('Ask console')}
        top={
          <TopBar
            title={threadTitle}
            actions={
              <>
                <button
                  type="button"
                  onClick={() => setSidecarOpen((open) => !open)}
                  data-open={sidecarOpen || undefined}
                  aria-expanded={sidecarOpen}
                  aria-label={t('Recent chats')}
                  title={t('Recent chats')}
                  className={ICON_BUTTON}
                >
                  <PanelRightIcon className="size-[18px]" />
                </button>
                <button
                  type="button"
                  onClick={newThread}
                  aria-label={t('New chat')}
                  title={t('New chat')}
                  className={ICON_BUTTON}
                >
                  <PencilSquareIcon className="size-4" />
                </button>
              </>
            }
          />
        }
        sidecar={
          <HistorySidecar
            open={sidecarOpen}
            threads={sessions}
            activeId={activeSessionId}
            openingId={openingId}
            rowError={rowError}
            loading={historyStatus === 'loading'}
            stale={historyStatus === 'stale'}
            onRefresh={() => void refreshSessions()}
            onOpen={openThread}
            onDelete={requestDelete}
          />
        }
      >
        {/* Transitions only — never a live region on the streamed markdown,
            which re-renders every animation frame. */}
        <p role="status" className="sr-only">
          {busy
            ? t('Reading the full text…')
            : lastGroup?.kind === 'qa' && lastGroup.answer
              ? lastGroup.answer.error
                ? t('The answer failed.')
                : t('Answer ready')
              : ''}
        </p>

        <div ref={bodyRef} className={clsx(BODY_CLASS, !hasConversation && EMPTY_BODY)}>
          {hasConversation && (
            <div
              ref={transcriptRef}
              onScroll={onScroll}
              className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pt-2"
            >
              <div ref={listRef} className="mx-auto w-[min(100%,768px)]">
                {groups.map((g) =>
                  g.kind === 'target' ? (
                    <TargetLine key={g.key} scope={g.scope} />
                  ) : (
                    <article
                      key={g.key}
                      data-live={!g.answer && busy ? '' : undefined}
                      className={clsx(
                        'pt-7 pb-2 last:min-h-(--turn-min)',
                        !g.answer && busy && 'animate-rise-in motion-reduce:animate-none',
                      )}
                    >
                      <AskedBubble turn={g.question} />
                      <div className="mt-5">
                        {g.answer ? (
                          <>
                            <SettledAnswer
                              turn={g.answer}
                              anchor={`vc-${g.key}`}
                              onRetry={
                                g === lastGroup && g.answer.error && !busy
                                  ? () => retryFrom(g.key)
                                  : undefined
                              }
                            />
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
                      </div>
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
                  'absolute bottom-[calc(var(--dock-top,6rem)+0.75rem)] left-1/2 z-[6] flex -translate-x-1/2 items-center gap-1.5 rounded-sm border border-line-strong bg-surface py-1.5 pr-2.5 pl-2 text-xs font-medium text-foreground',
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
                className={GREETING_WRAP}
              >
                <Greeting lead={t('What should we look into?')} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* The dock: composer + picker. Same element before and after the first question — it travels. */}
          <motion.div
            ref={dockRef}
            layout="position"
            transition={{ layout: { duration: reduceMotion ? 0 : 0.42, ease: EASE_IN_OUT } }}
            className={clsx(
              DOCK_WRAP,
              hasConversation &&
                'pt-3 before:pointer-events-none before:absolute before:-top-7 before:-right-6 before:-left-6 before:h-10 before:bg-gradient-to-b before:from-transparent before:to-surface',
            )}
          >
            <ComposerFrame
              onSubmit={(e) => {
                e.preventDefault()
                submit()
              }}
              attachment={
                target && (
                  <motion.span
                    initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.18, ease: EASE_OUT }}
                    className="inline-flex max-w-full items-center gap-1.5 rounded-sm bg-foreground/5 py-[3px] pr-1 pl-2"
                  >
                    <span
                      aria-hidden="true"
                      className="size-1.5 shrink-0 rounded-full"
                      style={{ backgroundColor: scoreColor(target.signal_score) }}
                    />
                    <span className="truncate text-xs font-medium text-foreground">
                      {shortTitle(target.title)}
                    </span>
                    <button
                      type="button"
                      onClick={unpick}
                      disabled={busy}
                      aria-label={t('Remove this paper')}
                      className="grid size-[18px] shrink-0 place-items-center rounded-full text-muted-foreground transition-colors duration-100 ease-out hover:bg-foreground/10 hover:text-foreground disabled:opacity-50"
                    >
                      <XMarkIcon className="size-3" />
                    </button>
                  </motion.span>
                )
              }
              leading={<ToolMenu onAttach={() => startPick()} disabled={busy} />}
              field={
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
                      : target
                        ? t('Ask about this paper…')
                        : t('Ask anything')
                  }
                  autoComplete="off"
                  spellCheck={false}
                  className={clsx(
                    FIELD_CLASS,
                    'text-foreground placeholder:text-muted-foreground focus:outline-none',
                  )}
                />
              }
              trailing={
                <button
                  type={busy ? 'button' : 'submit'}
                  onClick={busy ? stop : undefined}
                  aria-label={busy ? t('Stop') : t('Send')}
                  className={clsx(
                    'relative flex size-8 shrink-0 items-center justify-center rounded-sm transition-[background-color,color,transform] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.94]',
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
              }
            />

            {mode === 'pick' && (
              <PaperPicker
                entries={entries}
                matched={paletteMatched}
                total={paletteTotal}
                status={paletteStatus}
                query={pickQuery}
                cursor={cursor}
                placement={hasConversation ? 'above' : 'below'}
                onCursor={setCursor}
                onPick={pick}
                onRetry={retryPalette}
              />
            )}
          </motion.div>
        </div>
      </AskCanvas>

      {/* A failure keeps it open — a destructive action never fails silently. */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) {
            setPendingDelete(null)
            setDeleteError(null)
          }
        }}
      >
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            deleteTriggerRef.current?.focus()
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>{t('Delete this conversation?')}</AlertDialogTitle>
            <AlertDialogDescription>
              {fmt(t('"{title}" and every answer in it will be deleted. This cannot be undone.'), {
                title: pendingDelete ? shortTitle(pendingDelete.title) : '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && <ErrorNote>{deleteError}</ErrorNote>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{t('Cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleting}
              onClick={(event) => {
                // Radix closes on Action by default; we close only on success.
                event.preventDefault()
                void confirmDelete()
              }}
            >
              {deleting && <Spinner className="size-3.5" aria-hidden="true" />}
              {deleting ? t('Deleting…') : t('Delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

/** A bare target change: one quiet centered line, no rules, no card. */
function TargetLine({ scope }: { scope: AskScope }) {
  const t = useT()
  return (
    <p
      role="separator"
      className="pt-3.5 pb-1 text-center font-mono text-[11px] tracking-[0.05em] text-muted-foreground"
    >
      {t('Target')} →{' '}
      {scope.title
        ? fmt(t('{title} · full text'), { title: shortTitle(scope.title) })
        : t('All papers')}
    </p>
  )
}

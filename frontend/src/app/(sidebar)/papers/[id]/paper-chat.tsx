'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { LiveAnswer } from '@/components/live-answer'
import { Card, ErrorNote, SectionLabel } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
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
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { ScoredPaper } from '@/lib/papers/types'
import {
  ChatBubbleLeftRightIcon,
  ChevronDownIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  StopIcon,
  XMarkIcon,
} from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useReducedMotion } from 'motion/react'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import { ICON_BUTTON, PanelRightIcon } from '../../ask/console-frame'
import { HistoryList } from '../../ask/history-sidecar'
import { shortTitle } from '../../ask/types'
import { ScoreRailFrame, type RailParts } from './score-rail'
import { usePaperThread, type Msg } from './use-paper-thread'

/**
 * Ask this paper — the "Column" direction (picker of 9 Sep 2026).
 *
 * Closed, the rail is the score card (ScoreRailFrame) with the composer
 * card under it: title row, one line on scope, the question line, and —
 * once this paper has a thread — a `Continue "…"` line naming it. Open, the
 * rail widens from 300 to 400px (sections.tsx, via `:has`) and becomes ONE
 * console: the score card exactly as it was — score, bars, radar —
 * pinned at the top, the conversation scrolling beneath it, the composer at
 * the foot. Nothing of the card is pulled into the chat (asked for on 10
 * Sep 2026): the numbers and the radar keep their seats, are never covered
 * and never leave the screen — the whole point of the direction — and the
 * recent-chats list opens in the space beneath them, never over them.
 *
 * The thread outlives the surface: collapsing keeps it, the next open finds
 * it, and only "New chat" clears it. Everything about sessions, resume and
 * streaming is use-paper-thread.ts; this file is the layout and its motion.
 *
 * Below lg the rail stacks under the record and the console simply expands
 * in place — no sheet, no pill, no scroll lock.
 */

const LG = '(min-width: 1024px)'
const CONSOLE_TOP = 32 // lg:top-8 on the sticky rail
// Under this the console scrolls as a whole (the card, not just the thread),
// so the composer stays reachable on a short or zoomed viewport.
const CONSOLE_MIN = 240
const EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)'
const EASE_IN_OUT = 'cubic-bezier(0.77, 0, 0.175, 1)'

/**
 * Whether the chat can read the paper's body. The backend sends the OCR
 * markdown or the stored PDF; a paper whose PDF is still just a URL (most of
 * the corpus, 11 Sep 2026) gives the model the abstract and nothing more, and
 * the copy must not promise otherwise.
 */
function readsFullText(paper: Pick<ScoredPaper, 'pdf_key' | 'markdown_key'>): boolean {
  if (paper.markdown_key) return true
  return Boolean(paper.pdf_key && !/^https?:\/\//i.test(paper.pdf_key))
}

export function PaperChat({
  paper,
  rail,
  initialSessionId = null,
}: {
  paper: ScoredPaper
  /** The score card's parts, computed on the server (score-rail.tsx). */
  rail: RailParts
  /** A `?session=` from the URL: opens the console on that thread. */
  initialSessionId?: string | null
}) {
  const t = useT()
  const reduceMotion = useReducedMotion()
  const thread = usePaperThread({ paperId: paper.id, t, initialSessionId })

  // Open from the start when the URL names a thread; the FLIP has nothing to
  // move from then, and the layout effect below sees no `flipFrom`.
  const [open, setOpen] = useState(initialSessionId !== null)
  const [profileExpanded, setProfileExpanded] = useState(false)
  const [recentsOpen, setRecentsOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [input, setInput] = useState('')

  const consoleRef = useRef<HTMLDivElement>(null)
  const radarRef = useRef<HTMLDivElement>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const titleRef = useRef<HTMLButtonElement>(null)
  // The radar's rect before a layout switch, for the FLIP that follows it.
  const flipFrom = useRef<DOMRect | null>(null)

  const follow = useCallback(() => endRef.current?.scrollIntoView({ block: 'end' }), [])

  const show = useCallback(() => {
    if (open) return
    flipFrom.current = radarRef.current?.getBoundingClientRect() ?? null
    setOpen(true)
    void thread.ensureLoaded()
  }, [open, thread])

  // Collapsing unmounts the reveal, so an answer still running is filed in
  // full the moment its stream ends (settleBlind) rather than waiting for a
  // reveal that will never report.
  const { ensureLoaded, ask, settleBlind } = thread
  const hide = useCallback(() => {
    if (!open) return
    flipFrom.current = radarRef.current?.getBoundingClientRect() ?? null
    setRecentsOpen(false)
    setOpen(false)
    settleBlind()
  }, [open, settleBlind])

  /**
   * The layout switch is never animated — the grid re-wraps the record
   * once. The card keeps its shape; what moves is the radar, by the 50px the
   * wider column re-centres it (translate only; it keeps its size and its
   * labels must not distort). The console's new material is revealed
   * leftward so the page's right edge stays still; the thread fades in.
   */
  useLayoutEffect(() => {
    const from = flipFrom.current
    flipFrom.current = null
    if (reduceMotion || !from || !matchMedia(LG).matches) return
    const radar = radarRef.current
    if (radar) {
      const to = radar.getBoundingClientRect()
      const dx = from.left - to.left
      const dy = from.top - to.top
      if (Math.abs(dx) >= 1 || Math.abs(dy) >= 1) {
        radar.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], {
          duration: 280,
          easing: EASE_IN_OUT,
        })
      }
    }
    if (open) {
      consoleRef.current?.animate(
        [{ clipPath: 'inset(0 0 0 100px)' }, { clipPath: 'inset(0 0 0 0)' }],
        { duration: 260, easing: EASE_OUT },
      )
      threadRef.current?.animate([{ opacity: 0 }, { opacity: 1 }], {
        duration: 160,
        delay: 120,
        easing: 'ease-out',
        fill: 'backwards',
      })
    }
  }, [open, reduceMotion])

  // The console takes what is left of the viewport under the rail's top —
  // at y32 once the sticky wrapper is stuck, lower at the top of the page.
  useEffect(() => {
    if (!open) return
    const el = consoleRef.current
    if (!el) return
    let frame = 0
    const fit = () => {
      frame = 0
      if (!matchMedia(LG).matches) {
        el.style.height = ''
        return
      }
      const top = Math.max(CONSOLE_TOP, el.parentElement?.getBoundingClientRect().top ?? 0)
      el.style.height = `${Math.max(CONSOLE_MIN, window.innerHeight - top - CONSOLE_TOP)}px`
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(fit)
    }
    fit()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [open])

  // Open: focus the composer; Escape closes the list first, then the console.
  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 120)
    const onKey = (e: KeyboardEvent) => {
      // A dialog above the console (delete) takes its own Escape first.
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (recentsOpen) setRecentsOpen(false)
      else hide()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, recentsOpen, hide])

  // Collapse unmounts the control that had focus; it lands on the entry
  // card's title, the control that reopens the console.
  const wasOpen = useRef(open)
  useEffect(() => {
    if (!open && wasOpen.current) titleRef.current?.focus({ preventScroll: true })
    wasOpen.current = open
  }, [open])

  // A `?session=` link lands with the console already open (see useState
  // above); the thread it names is fetched here.
  useEffect(() => {
    if (initialSessionId) void ensureLoaded()
  }, [initialSessionId, ensureLoaded])

  // Keep the newest turn at the foot as the thread grows or a thread lands.
  useEffect(() => {
    if (open && thread.msgs.length > 0) follow()
  }, [open, thread.msgs, follow])

  /**
   * A question is sent once the resume has landed (instant after the first
   * open), so it joins the thread the card promised to continue rather than
   * opening a stray session beside it. The line is cleared only when the
   * question was taken — a refused one stays where it was typed.
   */
  const submit = useCallback(
    (q: string, clear: (q: string) => void) => {
      const question = q.trim()
      if (!question) return
      void ensureLoaded().then(() => {
        if (ask(question)) clear(q)
      })
    },
    [ensureLoaded, ask],
  )
  const clearDraft = useCallback((q: string) => setDraft((v) => (v === q ? '' : v)), [])
  const clearInput = useCallback((q: string) => setInput((v) => (v === q ? '' : v)), [])

  /** The entry card: a question typed under the score opens the console with it asked. */
  function askFromCard(e: FormEvent) {
    e.preventDefault()
    if (thread.asking) {
      thread.stop()
      return
    }
    if (!draft.trim()) return
    show()
    submit(draft, clearDraft)
  }

  function askFromConsole(e: FormEvent) {
    e.preventDefault()
    if (thread.asking) {
      thread.stop()
      return
    }
    submit(input, clearInput)
  }

  const label = fmt(t('Ask about {title}'), { title: paper.title })
  const count = thread.sessions.length
  const lastAnswer = thread.msgs.findLast((m) => m.role === 'scanner')
  const fullText = readsFullText(paper)
  const reading = fullText ? t('Reading the full text…') : t('Reading the abstract…')
  const scopeLine = fullText
    ? t('Answered from this paper alone.')
    : t("Answered from this paper's abstract only.")
  // Transitions only — never a live region on the streamed markdown, which
  // re-renders every animation frame (the same line the Ask page carries).
  const status = (
    <p role="status" className="sr-only">
      {thread.asking
        ? reading
        : lastAnswer
          ? lastAnswer.error
            ? t('The answer failed.')
            : t('Answer ready')
          : ''}
    </p>
  )
  const placeholder = thread.activeId ? t('Ask a follow-up…') : t('What would you like to know?')

  if (!open) {
    return (
      <>
        <ScoreRailFrame
          label={rail.label}
          score={rail.score}
          bars={rail.bars}
          radar={rail.radar && <div ref={radarRef}>{rail.radar}</div>}
        />
        <PaperChatFrame
          title={t('Ask this paper')}
          count={thread.historyStatus === 'ready' && count > 0 ? count : null}
          onOpen={show}
          titleRef={titleRef}
          hint={
            thread.asking ? (
              <span className="inline-flex items-center gap-2 text-foreground">
                <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
                {t('Answering…')}
              </span>
            ) : (
              scopeLine
            )
          }
          composer={
            <Composer
              name="rail-question"
              value={draft}
              onChange={setDraft}
              onSubmit={askFromCard}
              placeholder={placeholder}
              label={t('Ask a question about this paper')}
              send={t('Send')}
              stop={thread.asking ? t('Stop') : null}
            />
          }
          cont={
            thread.resumeTarget && (
              <>
                <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-accent" />
                <span className="truncate">
                  {fmt(t('Continue "{title}"'), { title: thread.resumeTarget.title })}
                </span>
              </>
            )
          }
        />
        {status}
        <DeleteDialog thread={thread} />
      </>
    )
  }

  const loadingThread = thread.openingId !== null && thread.msgs.length === 0
  const empty = thread.msgs.length === 0 && !thread.asking && !loadingThread

  return (
    <>
      <div
        ref={consoleRef}
        data-shape="paper-console"
        data-console-open=""
        role="region"
        aria-label={label}
        className="lg:flex lg:flex-col"
      >
        <Card flush className="flex min-h-0 flex-col overflow-hidden lg:h-full lg:overflow-y-auto">
          {/* The profile: the score card — collapsed by default in open console mode to preserve room */}
          <div data-row="profile" className="shrink-0 border-b border-line-soft px-5 py-3.5">
            <div className="flex items-baseline justify-between gap-4">
              <span className="font-mono text-[44px] leading-none font-medium tracking-tight text-zinc-950 tabular-nums dark:text-white">
                {rail.score}
              </span>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
                  {rail.label}
                </span>
                {rail.bars && (
                  <button
                    type="button"
                    onClick={() => setProfileExpanded((v) => !v)}
                    aria-expanded={profileExpanded}
                    aria-label={
                      profileExpanded ? t('Hide score breakdown') : t('Show score breakdown')
                    }
                    title={profileExpanded ? t('Hide score breakdown') : t('Show score breakdown')}
                    className="inline-flex size-6 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
                  >
                    <ChevronDownIcon
                      aria-hidden="true"
                      className={clsx(
                        'size-3.5 transition-transform duration-200',
                        profileExpanded && 'rotate-180',
                      )}
                    />
                  </button>
                )}
              </div>
            </div>
            {profileExpanded && (
              <div data-row="details" className="pt-2">
                <ul className="mt-2 space-y-0.5">{rail.bars}</ul>
                {rail.radar && (
                  <div className="mt-4 flex justify-center border-t border-line-soft pt-4">
                    <div ref={radarRef}>{rail.radar}</div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div
            data-row="head"
            className="flex shrink-0 flex-wrap items-center gap-x-2 border-b border-line-soft py-1.5 pr-2 pl-4"
          >
            <div className="flex min-w-0 flex-1 items-center gap-2 font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase">
              <ChatBubbleLeftRightIcon
                aria-hidden="true"
                className="size-3.5 shrink-0 text-accent"
              />
              {t('Ask this paper')}
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              <button
                type="button"
                onClick={() => {
                  // A list that failed to load is tried again when asked for.
                  if (!recentsOpen && thread.historyStatus === 'stale') void thread.retryHistory()
                  setRecentsOpen((v) => !v)
                }}
                data-open={recentsOpen || undefined}
                aria-expanded={recentsOpen}
                aria-label={t('Recent chats')}
                title={t('Recent chats')}
                className={ICON_BUTTON}
              >
                <PanelRightIcon className="size-[18px]" />
              </button>
              <button
                type="button"
                onClick={() => {
                  thread.newChat()
                  setRecentsOpen(false)
                  inputRef.current?.focus()
                }}
                disabled={thread.activeId === null && thread.msgs.length === 0}
                aria-label={t('New chat')}
                title={t('New chat')}
                className={ICON_BUTTON}
              >
                <PencilSquareIcon className="size-4" />
              </button>
              <button
                type="button"
                onClick={hide}
                aria-label={t('Collapse')}
                title={t('Collapse')}
                className={ICON_BUTTON}
              >
                <XMarkIcon className="size-4" />
              </button>
            </div>
            <div className="mt-0.5 basis-full truncate pb-1 text-[13px] font-semibold tracking-tight">
              {thread.title}
            </div>
          </div>

          {/* The scroller: the thread alone. The list overlays this and only this. */}
          <div className="relative min-h-0 flex-1 lg:min-h-40">
            {/* Inert under the list, so Tab cannot land on the bars it covers. */}
            <div
              inert={recentsOpen}
              className="overscroll-contain px-5 pt-3 pb-4 lg:h-full lg:overflow-y-auto"
            >
              <div ref={threadRef} className="max-lg:min-h-[50dvh]">
                {loadingThread ? (
                  <p className="text-[13px] leading-relaxed text-muted-foreground">
                    <Bone.Text lines={3} widths={['92%', '100%', '48%']} />
                  </p>
                ) : empty ? (
                  <p className="text-[13px] leading-relaxed text-balance text-muted-foreground">
                    {scopeLine}
                  </p>
                ) : (
                  <Thread
                    msgs={thread.msgs}
                    asking={thread.asking}
                    live={thread.live}
                    askSeq={thread.askSeq}
                    scanning={reading}
                    onGrow={follow}
                    onRevealed={thread.onRevealed}
                    endRef={endRef}
                  />
                )}
              </div>
            </div>

            <Recents open={recentsOpen} thread={thread} onOpened={() => setRecentsOpen(false)} />
          </div>

          <Composer
            inputRef={inputRef}
            name="question"
            value={input}
            onChange={setInput}
            onSubmit={askFromConsole}
            placeholder={placeholder}
            label={t('Ask a question about this paper')}
            send={t('Send')}
            stop={thread.asking ? t('Stop') : null}
          />
        </Card>
      </div>
      {status}
      <DeleteDialog thread={thread} />
    </>
  )
}

type ThreadState = ReturnType<typeof usePaperThread>

function Thread({
  msgs,
  asking,
  live,
  askSeq,
  scanning,
  onGrow,
  onRevealed,
  endRef,
}: {
  msgs: Msg[]
  asking: boolean
  live: ThreadState['live']
  askSeq: number
  /** What the reveal says before the first token ("Reading the full text…" or the abstract line). */
  scanning: string
  onGrow: () => void
  onRevealed: () => void
  endRef: RefObject<HTMLDivElement | null>
}) {
  const t = useT()
  return (
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
            {m.stopped && !m.error && (
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">{t('Stopped')}</p>
            )}
          </div>
        ),
      )}
      {asking && (
        <LiveAnswer
          key={askSeq}
          state={live}
          scanning={scanning}
          className="text-[13px] text-muted-foreground"
          onGrow={onGrow}
          onRevealed={onRevealed}
        />
      )}
      <div ref={endRef} aria-hidden="true" />
    </div>
  )
}

/**
 * Recent chats about this paper, in the space beneath the radar: over the
 * bars and the thread, never over the profile or the composer. Full width
 * of the console — at 400px a sliver would leave no usable transcript.
 */
function Recents({
  open,
  thread,
  onOpened,
}: {
  open: boolean
  thread: ThreadState
  onOpened: () => void
}) {
  const t = useT()
  const n = thread.sessions.length
  return (
    <div
      role="region"
      inert={!open}
      aria-hidden={!open}
      aria-label={t('Recent chats')}
      className={clsx(
        'absolute inset-0 z-10 flex flex-col bg-surface transition-[opacity,transform] duration-150 ease-out motion-reduce:transition-none',
        open ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-1.5 opacity-0',
      )}
    >
      <div className="flex shrink-0 items-baseline justify-between px-4 pt-3 pb-1.5">
        <SectionLabel className="text-[11px]">{t('Recent')}</SectionLabel>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
          {n === 1 ? t('1 chat') : fmt(t('{count} chats'), { count: n })}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-2">
        {thread.historyStatus === 'loading' ? (
          <p className="px-3 py-4 text-xs text-muted-foreground">
            <Bone.Text lines={2} widths={['80%', '55%']} />
          </p>
        ) : (
          <HistoryList
            threads={thread.sessions}
            activeId={thread.activeId}
            openingId={thread.openingId}
            rowError={thread.rowError}
            onOpen={(s) => {
              void thread.openThread(s).then((opened) => {
                if (opened) onOpened()
              })
            }}
            onDelete={thread.requestDelete}
            meta="count"
            empty={t('Questions about this paper are filed here.')}
          />
        )}
        {thread.historyStatus === 'stale' && (
          <p className="px-3 pt-2 text-[11px] text-muted-foreground">
            {t('History may be out of date.')}
          </p>
        )}
      </div>
    </div>
  )
}

/** The shipped copy, unchanged; a failure keeps it open. */
function DeleteDialog({ thread }: { thread: ThreadState }) {
  const t = useT()
  return (
    <AlertDialog
      open={thread.pendingDelete !== null}
      onOpenChange={(open) => {
        if (!open) thread.cancelDelete()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('Delete this conversation?')}</AlertDialogTitle>
          <AlertDialogDescription>
            {fmt(t('"{title}" and every answer in it will be deleted. This cannot be undone.'), {
              title: thread.pendingDelete ? shortTitle(thread.pendingDelete.title) : '',
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {thread.deleteError && <ErrorNote>{thread.deleteError}</ErrorNote>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={thread.deleting}>{t('Cancel')}</AlertDialogCancel>
          <AlertDialogAction
            disabled={thread.deleting}
            onClick={(event) => {
              // Radix closes on Action by default; we close only on success.
              event.preventDefault()
              void thread.confirmDelete()
            }}
          >
            {thread.deleting && <Spinner className="size-3.5" aria-hidden="true" />}
            {thread.deleting ? t('Deleting…') : t('Delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/**
 * One question line with a send button, under a hairline — the same row in
 * the entry card and at the foot of the console. With `stop` set the button
 * is Stop: an answer is streaming and the thread now outlives the surface,
 * so the reader can always end it.
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
  stop = null,
}: {
  inputRef?: RefObject<HTMLInputElement | null>
  name: string
  value: string
  onChange: (value: string) => void
  onSubmit: (e: FormEvent) => void
  placeholder: string
  label: string
  send: string
  /** The Stop label while an answer streams; null offers Send. */
  stop?: string | null
}) {
  const ready = value.trim() !== ''
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
          aria-label={stop ?? send}
          className={clsx(
            'flex size-8 shrink-0 items-center justify-center rounded-full transition-[background-color,color,transform] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.97]',
            stop || ready
              ? 'bg-foreground text-background hover:bg-foreground/85'
              : 'bg-foreground/10 text-muted-foreground',
          )}
        >
          {stop ? <StopIcon className="size-4" /> : <PaperAirplaneIcon className="size-4" />}
        </button>
      </div>
    </form>
  )
}

/**
 * The entry card under the score card: the title row (a button that opens
 * the console, with the paper's chat count), one line on scope, the
 * question line, and the continue line naming the thread the next question
 * joins. PaperChat and PaperChatSkeleton both fill it.
 */
export function PaperChatFrame({
  state = 'loaded',
  title,
  count,
  onOpen,
  titleRef,
  hint,
  composer,
  cont,
}: {
  state?: 'loaded' | 'skeleton'
  title: string
  /** How many chats this paper has; null until the list is known. */
  count: ReactNode
  onOpen?: () => void
  titleRef?: RefObject<HTMLButtonElement | null>
  /** The one line under the card's title saying what the answers draw on. */
  hint: ReactNode
  /** The rail's question line. */
  composer: ReactNode
  /** The continue line's content; falsy hides the row. */
  cont?: ReactNode
}) {
  return (
    <Card
      flush
      data-shape="paper-chat-composer"
      data-state={state}
      className="mt-3 overflow-hidden"
    >
      <button
        ref={titleRef}
        type="button"
        data-row="title"
        onClick={onOpen}
        disabled={!onOpen}
        aria-expanded={false}
        className="flex w-full items-center gap-2 px-4 pt-3 text-left font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase transition-transform duration-150 ease-out focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent active:scale-[0.985]"
      >
        <ChatBubbleLeftRightIcon aria-hidden="true" className="size-3.5 shrink-0 text-accent" />
        {title}
        <span className="ml-auto font-mono text-[11px] tracking-normal text-zinc-400 tabular-nums dark:text-zinc-500">
          {count}
        </span>
      </button>
      <p
        data-row="hint"
        onClick={onOpen}
        className={clsx(
          'px-4 pt-1.5 pb-2.5 text-xs text-muted-foreground',
          onOpen && 'group-has-[[data-comments-open]]/record:cursor-pointer',
        )}
      >
        {hint}
      </p>
      <div className="transition-all duration-150 group-has-[[data-comments-open]]/record:hidden">
        {composer}
        {cont && (
          <p
            data-row="continue"
            className="flex items-center gap-2 border-t border-line-soft px-4 py-2 text-xs text-zinc-600 dark:text-zinc-300"
          >
            {cont}
          </p>
        )}
      </div>
    </Card>
  )
}

/** Before the record arrives: the composer card with its rows boned. */
export function PaperChatSkeleton({ title }: { title: string }) {
  return (
    <PaperChatFrame
      state="skeleton"
      title={title}
      count={<Bone.Text widths={['1ch']} />}
      hint={<Bone.Text widths={['26ch']} />}
      composer={
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

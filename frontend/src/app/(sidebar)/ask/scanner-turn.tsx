'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { ErrorNote } from '@/components/scanner-ui'
import type { ChatStreamState } from '@/lib/chat/use-chat-stream'
import { useSmoothText } from '@/lib/chat/use-smooth-text'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { CheckCircleIcon } from '@heroicons/react/16/solid'
import { motion, useReducedMotion } from 'motion/react'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { MiniScore } from './paper-picker'
import { shortTitle, type AnswerTurn, type QuestionTurn } from './types'

const EASE_OUT = [0.23, 1, 0.32, 1] as const

/**
 * A user question, right-aligned in a quiet bubble. The scope it was asked
 * under is a title attribute rather than a visible eyebrow: on a chat canvas
 * the paper is already named in the composer's chip and in the sidecar row,
 * and a mono line over every question turned the transcript into a ledger.
 */
export function AskedBubble({ turn }: { turn: QuestionTurn }) {
  const t = useT()
  const scope = turn.scope.title
    ? fmt(t('Asked {time} · {title} · full text'), {
        time: turn.askedAt,
        title: shortTitle(turn.scope.title),
      })
    : fmt(t('Asked {time} · all papers'), { time: turn.askedAt })
  return (
    <div className="flex justify-end">
      <h3
        title={scope}
        className="bg-foreground/6 text-foreground max-w-[80%] rounded-sm px-3.5 py-2 text-[15px] leading-relaxed font-normal text-pretty"
      >
        {turn.text}
      </h3>
    </div>
  )
}

function useElapsed(active: boolean) {
  const [ms, setMs] = useState(0)
  useEffect(() => {
    if (!active) return
    const t0 = performance.now()
    const id = window.setInterval(() => setMs(performance.now() - t0), 100)
    return () => window.clearInterval(id)
  }, [active])
  return ms
}

/** Retrieval status shown until the first word arrives, with the wait counted. */
function ScanningLine({ scopeTitle }: { scopeTitle: string | null }) {
  const t = useT()
  const ms = useElapsed(true)
  return (
    <p className="text-muted-foreground mt-1 flex items-center gap-2 font-mono text-xs tabular-nums">
      <span className="relative flex size-2 shrink-0">
        <span className="bg-accent/60 absolute inset-0 animate-ping rounded-full" />
        <span className="bg-accent relative size-2 rounded-full" />
      </span>
      <span className="min-w-0 truncate">
        {scopeTitle
          ? fmt(t('Reading “{title}” · full text'), { title: scopeTitle })
          : t('Reading the full text…')}
      </span>
      <span className="ml-auto shrink-0">{(ms / 1000).toFixed(1)}s</span>
    </p>
  )
}

/**
 * The in-flight answer. Streamed text is revealed at a steady word cadence and
 * each word unveils out of a blur; the scanning line holds until the first
 * word. Settlement happens in the transcript once `onRevealed` reports that
 * the stream has finished and every word is on screen.
 */
export function LiveAnswer({
  state,
  scopeTitle,
  onGrow,
  onRevealed,
}: {
  state: ChatStreamState
  scopeTitle: string | null
  /** Called as words land, so the transcript can follow. */
  onGrow: () => void
  /** The stream has finished and the reveal has caught up with it. */
  onRevealed: () => void
}) {
  const t = useT()
  const shown = useSmoothText(state.text, state.status)
  const finished = state.status === 'done' || state.status === 'error'

  useEffect(() => {
    if (shown.text) onGrow()
  }, [shown.text, onGrow])

  useEffect(() => {
    if (finished && shown.caughtUp) onRevealed()
  }, [finished, shown.caughtUp, onRevealed])

  if (state.status === 'idle') return null
  if (shown.text === '') return <ScanningLine scopeTitle={scopeTitle} />
  // Visual citations land after the last delta, so chips render without ticks
  // until then.
  return (
    <AnswerMarkdown
      text={shown.text}
      streaming
      unveil
      caret={false}
      citations={state.visualCitations}
      t={t}
      className="text-foreground text-[15px]"
    />
  )
}

/**
 * A settled answer: body plus citations / visual evidence / fact check.
 * `anchor` is the DOM id prefix that ties inline citation chips to the
 * visual-evidence rows below. A failed turn keeps whatever streamed — the
 * partial prose renders above the error, with `onRetry` as its one action —
 * and suppresses the extras (a fact-check line under an unfinished answer
 * misleads).
 */
export function SettledAnswer({
  turn,
  anchor,
  onRetry,
}: {
  turn: AnswerTurn
  anchor: string
  onRetry?: () => void
}) {
  const t = useT()
  if (turn.error) {
    return (
      <div className="min-w-0">
        {turn.text !== '' && (
          <AnswerMarkdown
            text={turn.text}
            citations={[]}
            t={t}
            className="text-foreground mb-3 text-[15px]"
          />
        )}
        <ErrorNote
          action={
            onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="bg-foreground text-background hover:bg-foreground/85 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors"
              >
                {t('Ask again')}
              </button>
            )
          }
        >
          {turn.text !== '' ? t('The answer stopped part-way through.') : turn.error}
        </ErrorNote>
      </div>
    )
  }
  return (
    <div className="min-w-0">
      <AnswerMarkdown
        text={turn.text}
        citations={turn.visualCitations}
        citationAnchor={anchor}
        t={t}
        className="text-foreground text-[15px]"
      />
      {turn.stopped && (
        <p className="text-muted-foreground mt-2 font-mono text-[11px]">{t('Stopped')}</p>
      )}
      <TurnExtras turn={turn} anchor={anchor} />
    </div>
  )
}

const item = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: EASE_OUT } },
}

/**
 * Citations, page evidence and the fact-check line. For an answer that just
 * settled, the block opens as one soft expansion and its pieces arrive inside
 * it one after another; loaded history renders settled. Inline citation chips
 * link here via `${anchor}-${i}` ids.
 */
function TurnExtras({ turn, anchor }: { turn: AnswerTurn; anchor: string }) {
  const t = useT()
  const reduceMotion = useReducedMotion()
  const hasExtras =
    turn.citations.length > 0 ||
    turn.visualCitations.length > 0 ||
    turn.factCheck !== null ||
    turn.usage !== null
  if (!hasExtras) return null

  const animate = Boolean(turn.arrived) && !reduceMotion
  const body = (
    <motion.div
      initial={animate ? 'hidden' : false}
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.09, delayChildren: 0.08 } } }}
      className="mt-3 space-y-1.5"
    >
      {turn.citations.map((cite) => (
        <motion.div key={cite.paper_id} variants={item}>
          <Link
            href={cite.href}
            className="border-line/70 hover:border-line flex min-w-0 items-center gap-2 rounded-sm border px-3 py-2 text-xs"
          >
            <MiniScore score={cite.signal_score} />
            <span className="text-foreground truncate font-medium">{cite.title}</span>
          </Link>
        </motion.div>
      ))}

      {turn.visualCitations.length > 0 && (
        <motion.div
          variants={item}
          className="border-line/70 space-y-1 rounded-sm border px-3 py-2"
        >
          {turn.visualCitations.map((v, i) => (
            <p
              key={i}
              id={`${anchor}-${i}`}
              className="text-muted-foreground flex min-w-0 scroll-mt-24 items-baseline gap-1.5 text-[11px]"
            >
              <span className="shrink-0 font-mono tabular-nums">
                {v.page != null ? fmt(t('p. {n}'), { n: v.page }) : '—'}
                {v.label ? ` · ${v.label}` : ''}
              </span>
              {v.quote && <span className="truncate italic">“{v.quote}”</span>}
              {v.verified_in_source && (
                <CheckCircleIcon
                  className="text-accent size-3.5 shrink-0 self-center"
                  aria-label={t('Verified in source')}
                />
              )}
            </p>
          ))}
        </motion.div>
      )}

      {(turn.factCheck || turn.usage) && (
        <motion.p
          variants={item}
          className="text-muted-foreground pt-0.5 font-mono text-[11px] tabular-nums"
        >
          {turn.factCheck && (
            <>
              {t('Fact check')} {turn.factCheck.verified ? t('passed') : t('flagged')} ·{' '}
              {fmt(t('{n} of {total} claims grounded'), {
                n: turn.factCheck.verified_count,
                total: turn.factCheck.total_count,
              })}
            </>
          )}
          {turn.factCheck && turn.usage?.total_tokens != null && ' · '}
          {turn.usage?.total_tokens != null &&
            fmt(t('{n} tokens'), { n: turn.usage.total_tokens.toLocaleString() })}
        </motion.p>
      )}
    </motion.div>
  )

  if (!animate) return body
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      transition={{ duration: 0.38, ease: EASE_OUT }}
      className="overflow-hidden"
    >
      {body}
    </motion.div>
  )
}

const FOLLOW_UPS = [
  'What does this actually enable?',
  'What is the strongest counter-argument?',
  'What would it take to use this at case scale?',
  'Which claims are weakest?',
]

/** The next questions, offered under the newest settled answer. */
export function FollowUps({ exclude, onAsk }: { exclude: string; onAsk: (q: string) => void }) {
  const t = useT()
  const reduceMotion = useReducedMotion()
  const pool = FOLLOW_UPS.map((q) => t(q))
    .filter((q) => q !== exclude)
    .slice(0, 3)
  return (
    <motion.div
      initial={reduceMotion ? false : 'hidden'}
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.04, delayChildren: 0.3 } } }}
      className="mt-3.5 flex flex-wrap gap-1.5"
    >
      {pool.map((q) => (
        <motion.button
          key={q}
          variants={item}
          type="button"
          onClick={() => onAsk(q)}
          className="border-line text-muted-foreground hover:border-line-strong hover:text-foreground hover:bg-foreground/3 rounded-sm border px-2.5 py-1.5 text-left text-xs transition-colors duration-100 ease-out active:scale-[0.98]"
        >
          {q}
        </motion.button>
      ))}
    </motion.div>
  )
}

'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { LiveAnswer as SharedLiveAnswer } from '@/components/live-answer'
import { ErrorNote } from '@/components/scanner-ui'
import type { ChatStreamState } from '@/lib/chat/use-chat-stream'
import { fmt, formatNumber } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { CheckCircleIcon } from '@heroicons/react/16/solid'
import { motion, useReducedMotion } from 'motion/react'
import Link from 'next/link'
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
        className="max-w-[80%] rounded-sm bg-foreground/6 px-3.5 py-2 text-[15px] leading-relaxed font-normal text-pretty text-foreground"
      >
        {turn.text}
      </h3>
    </div>
  )
}

/**
 * The in-flight answer on the Ask canvas: the shared reveal, with the scope
 * named in the scanning line.
 */
export function LiveAnswer({
  state,
  scopeTitle,
  onGrow,
  onRevealed,
}: {
  state: ChatStreamState
  scopeTitle: string | null
  onGrow: () => void
  onRevealed: () => void
}) {
  const t = useT()
  return (
    <SharedLiveAnswer
      state={state}
      scanning={
        scopeTitle
          ? fmt(t('Reading “{title}” · full text'), { title: scopeTitle })
          : t('Reading the full text…')
      }
      className="text-[15px] text-foreground"
      onGrow={onGrow}
      onRevealed={onRevealed}
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
            className="mb-3 text-[15px] text-foreground"
          />
        )}
        <ErrorNote
          action={
            onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="rounded-sm bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
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
        className="text-[15px] text-foreground"
      />
      {turn.stopped && (
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">{t('Stopped')}</p>
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
  const { lang } = useLanguage()
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
            className="flex min-w-0 items-center gap-2 rounded-sm border border-line/70 px-3 py-2 text-xs hover:border-line"
          >
            <MiniScore score={cite.signal_score} />
            <span className="truncate font-medium text-foreground">{cite.title}</span>
          </Link>
        </motion.div>
      ))}

      {turn.visualCitations.length > 0 && (
        <motion.div
          variants={item}
          className="space-y-1 rounded-sm border border-line/70 px-3 py-2"
        >
          {turn.visualCitations.map((v, i) => (
            <p
              key={i}
              id={`${anchor}-${i}`}
              className="flex min-w-0 scroll-mt-24 items-baseline gap-1.5 text-[11px] text-muted-foreground"
            >
              <span className="shrink-0 font-mono tabular-nums">
                {v.page != null ? fmt(t('p. {n}'), { n: v.page }) : '—'}
                {v.label ? ` · ${v.label}` : ''}
              </span>
              {v.quote && <span className="truncate italic">“{v.quote}”</span>}
              {v.verified_in_source && (
                <CheckCircleIcon
                  className="size-3.5 shrink-0 self-center text-accent"
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
          className="pt-0.5 font-mono text-[11px] text-muted-foreground tabular-nums"
        >
          {turn.factCheck && (
            <>
              {t('Fact check')} {turn.factCheck.verified ? t('passed') : t('flagged')} ·{' '}
              {fmt(t('{n} of {total} claims grounded'), {
                n: formatNumber(turn.factCheck.verified_count, lang),
                total: formatNumber(turn.factCheck.total_count, lang),
              })}
            </>
          )}
          {turn.factCheck && turn.usage?.total_tokens != null && ' · '}
          {turn.usage?.total_tokens != null &&
            fmt(t('{n} tokens'), { n: formatNumber(turn.usage.total_tokens, lang) })}
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
          className="rounded-sm border border-line px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors duration-100 ease-out hover:border-line-strong hover:bg-foreground/3 hover:text-foreground active:scale-[0.98]"
        >
          {q}
        </motion.button>
      ))}
    </motion.div>
  )
}

'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { SignalScore } from '@/components/scanner-ui'
import type { ChatStreamState } from '@/lib/chat/use-chat-stream'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/16/solid'
import { motion } from 'motion/react'
import Link from 'next/link'
import { useEffect } from 'react'
import { shortTitle, type AnswerTurn, type QuestionTurn } from './types'

/**
 * A user question, rendered as a scoped memo heading: a mono eyebrow carrying
 * time + scope, then the question itself. Scope lives in every eyebrow, so
 * mid-thread target changes read naturally without a divider.
 */
export function AskedHeading({ turn, divider }: { turn: QuestionTurn; divider?: boolean }) {
  const t = useT()
  return (
    <div>
      {divider && (
        <div className="mb-4 flex items-center gap-3">
          <span aria-hidden="true" className="bg-line-soft h-px flex-1" />
          <span className="text-muted-foreground shrink-0 font-mono text-[11px] tabular-nums">
            {turn.askedAt}
          </span>
        </div>
      )}
      <p className="text-muted-foreground flex min-w-0 items-center gap-1.5 font-mono text-[11px] tracking-[0.07em] uppercase tabular-nums">
        <span className="shrink-0">
          {divider ? t('Asked') : fmt(t('Asked {time}'), { time: turn.askedAt })}
        </span>
        <span aria-hidden="true">·</span>
        {turn.scope.title ? (
          <>
            <span className="bg-accent size-1.5 shrink-0 rounded-full" />
            <span className="truncate">{shortTitle(turn.scope.title)}</span>
            <span aria-hidden="true">·</span>
            <span className="shrink-0">{t('full text')}</span>
          </>
        ) : (
          <span className="truncate">{t('All papers')}</span>
        )}
      </p>
      <h3 className="text-foreground mt-1.5 text-[15px] font-semibold tracking-tight text-pretty">
        {turn.text}
      </h3>
    </div>
  )
}

/** Transient retrieval status shown until the first token arrives. */
function ScanningLine({
  scopeTitle,
  corpusCount,
}: {
  scopeTitle: string | null
  corpusCount: number
}) {
  const t = useT()
  return (
    <p className="text-muted-foreground mt-1.5 flex items-center gap-2 font-mono text-xs tabular-nums">
      <span className="relative flex size-2 shrink-0">
        <span className="bg-accent/60 absolute inset-0 animate-ping rounded-full" />
        <span className="bg-accent relative size-2 rounded-full" />
      </span>
      <span className="truncate">
        {scopeTitle
          ? fmt(t('Reading “{title}” · full text'), { title: scopeTitle })
          : fmt(t('Scanning {n} papers'), { n: corpusCount })}
      </span>
    </p>
  )
}

/**
 * The in-flight answer, driven by the live stream state: connecting shows the
 * scanning line, streamed markdown grows with a caret. Settlement (extras,
 * error states) happens in the transcript once the parent converts the stream
 * into an AnswerTurn.
 */
export function LiveAnswer({
  state,
  scopeTitle,
  corpusCount,
  onGrow,
}: {
  state: ChatStreamState
  scopeTitle: string | null
  corpusCount: number
  onGrow: () => void
}) {
  const t = useT()
  // Keep the transcript pinned to the newest words while streaming.
  useEffect(() => {
    if (state.text) onGrow()
  }, [state.text, onGrow])

  if (state.status === 'idle') return null
  if (state.status === 'connecting' || state.text === '') {
    return <ScanningLine scopeTitle={scopeTitle} corpusCount={corpusCount} />
  }
  // Visual citations land after the last delta, so chips render without ticks
  // until then.
  return (
    <AnswerMarkdown
      text={state.text}
      streaming={state.status === 'streaming'}
      citations={state.visualCitations}
      t={t}
      className="text-foreground/75 text-sm"
    />
  )
}

/**
 * A settled scanner answer: body plus citations / visual evidence / fact check.
 * `anchor` is the DOM id prefix that ties inline citation chips to the
 * visual-evidence rows below.
 */
export function SettledAnswer({
  turn,
  anchor,
  onDigIn,
}: {
  turn: AnswerTurn
  anchor: string
  onDigIn: (paperId: string) => void
}) {
  const t = useT()
  if (turn.error) {
    return (
      <div className="border-warn/40 bg-warn/5 flex items-start gap-2 rounded-sm border px-3 py-2.5">
        <ExclamationTriangleIcon className="text-warn mt-0.5 size-4 shrink-0" />
        <p className="text-foreground/80 text-sm leading-relaxed">{turn.error}</p>
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
        className="text-foreground/75 text-sm"
      />
      <TurnExtras turn={turn} anchor={anchor} onDigIn={onDigIn} />
    </div>
  )
}

const item = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' as const } },
}

function TurnExtras({
  turn,
  anchor,
  onDigIn,
}: {
  turn: AnswerTurn
  anchor: string
  onDigIn: (paperId: string) => void
}) {
  const t = useT()
  const hasExtras =
    turn.citations.length > 0 ||
    turn.visualCitations.length > 0 ||
    turn.factCheck !== null ||
    turn.usage !== null
  if (!hasExtras) return null

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.07 } } }}
      className="mt-3 space-y-1.5"
    >
      {turn.citations.map((cite) => (
        <motion.div
          key={cite.paper_id}
          variants={item}
          className="border-line/70 hover:border-line flex items-center gap-1 rounded-sm border pr-1.5"
        >
          <Link
            href={cite.href}
            className="flex min-w-0 flex-1 items-center gap-2 py-2 pl-3 text-xs"
          >
            <SignalScore score={cite.signal_score} size="sm" />
            <span className="text-foreground truncate font-medium">{cite.title}</span>
          </Link>
          <button
            type="button"
            onClick={() => onDigIn(cite.paper_id)}
            title={t('Target the conversation at this paper')}
            className="hover:bg-accent/10 shrink-0 rounded-sm px-2 py-1 text-xs font-medium text-blue-700"
          >
            {t('Dig in')}
          </button>
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
}

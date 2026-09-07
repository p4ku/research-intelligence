'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { Bone } from '@/components/skeleton'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { Dimension } from '@/lib/papers/types'
import { ChevronRightIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useState, type ReactNode } from 'react'

/**
 * The assessment: one row per dimension — its name, the first line of the
 * model's rationale as a teaser, the value — that opens in place to the full
 * rationale, the evidence it quoted, and the confidence line. The rail beside
 * it carries the bars, so the rows carry the reasoning.
 *
 * AssessmentRowsFrame / AssessmentRowFrame own the layout; AssessmentRows fills
 * them with data and AssessmentRowsSkeleton with bones.
 */

export function AssessmentRowsFrame({
  state = 'loaded',
  children,
}: {
  state?: 'loaded' | 'skeleton'
  children: ReactNode
}) {
  return (
    <div data-shape="assessment" data-state={state} className="border-t border-line">
      {children}
    </div>
  )
}

export function AssessmentRowFrame({
  open = false,
  onToggle,
  name,
  teaser,
  value,
  body,
}: {
  open?: boolean
  onToggle?: () => void
  name: ReactNode
  teaser: ReactNode
  value: ReactNode
  body?: ReactNode
}) {
  return (
    <div data-row="dimension" className="border-b border-line-soft">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        disabled={!onToggle}
        className="group grid w-full grid-cols-[minmax(0,1fr)_auto_14px] items-center gap-4 py-3.5 text-left"
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-zinc-950 dark:text-white">{name}</span>
          <span
            className={clsx(
              'mt-0.5 block truncate text-[13px] leading-normal text-zinc-500 dark:text-zinc-400',
              open && 'hidden',
            )}
          >
            {teaser}
          </span>
        </span>
        <span className="font-mono text-xl leading-none font-medium text-zinc-950 tabular-nums dark:text-white">
          {value}
        </span>
        <ChevronRightIcon
          aria-hidden="true"
          className={clsx(
            'size-3.5 text-zinc-400 transition-transform duration-200 ease-out motion-reduce:transition-none',
            open && 'rotate-90',
          )}
        />
      </button>
      <div
        className={clsx(
          'grid transition-[grid-template-rows] duration-[240ms] ease-out motion-reduce:transition-none',
          open ? '[grid-template-rows:1fr]' : '[grid-template-rows:0fr]',
        )}
      >
        <div className="overflow-hidden">{body}</div>
      </div>
    </div>
  )
}

/** The value as the row shows it: the number, or the raw string when there is none. */
function shownValue(d: Dimension): ReactNode {
  if (d.value === null) return <span className="text-zinc-500 dark:text-zinc-400">{d.raw}</span>
  const n = Number.isInteger(d.value)
    ? String(d.value)
    : (Math.round(d.value * 100) / 100).toString()
  return (
    <>
      {n}
      {d.max !== null && d.max !== 100 && (
        <span className="text-[11px] font-normal text-zinc-400">/{d.max}</span>
      )}
    </>
  )
}

/** The teaser is the rationale with its markdown emphasis stripped. */
function plain(text: string): string {
  return text
    .replace(/[*_`]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function Row({ dimension: d }: { dimension: Dimension }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const conf =
    typeof d.confidence === 'number'
      ? d.confidence <= 1
        ? `${Math.round(d.confidence * 100)}%`
        : String(d.confidence)
      : null
  const review =
    d.review_required || d.validation_status === 'warn' || d.validation_status === 'fail'
  return (
    <AssessmentRowFrame
      open={open}
      onToggle={() => setOpen((v) => !v)}
      name={d.name}
      teaser={d.rationale ? plain(d.rationale) : t('No rationale recorded.')}
      value={shownValue(d)}
      body={
        <div className="pr-10 pb-5 text-[13.5px]">
          {d.rationale ? (
            <AnswerMarkdown
              text={d.rationale}
              className="leading-relaxed text-zinc-600 dark:text-zinc-300"
            />
          ) : (
            <p className="text-zinc-400">{t('No rationale recorded.')}</p>
          )}
          {d.evidence && d.evidence.length > 0 && (
            <ul className="mt-3 space-y-2">
              {d.evidence.map((quote, i) => (
                <li
                  key={i}
                  className="border-l-2 border-line-soft pl-2.5 text-xs leading-relaxed text-zinc-500 italic dark:text-zinc-400"
                >
                  “{quote}”
                </li>
              ))}
            </ul>
          )}
          {(conf || review) && (
            <p className="mt-3.5 flex flex-wrap gap-x-2 font-mono text-[10px] tracking-[0.14em] text-zinc-400 uppercase">
              {conf && <span>{fmt(t('Confidence {n}'), { n: conf })}</span>}
              {conf && review && <span>·</span>}
              {review && <span>{t('Needs review')}</span>}
            </p>
          )}
        </div>
      }
    />
  )
}

export function AssessmentRows({ dimensions }: { dimensions: Dimension[] }) {
  const t = useT()
  if (dimensions.length === 0) {
    return (
      <AssessmentRowsFrame>
        <p className="py-4 text-sm text-zinc-400">{t('Not scored yet')}</p>
      </AssessmentRowsFrame>
    )
  }
  return (
    <AssessmentRowsFrame>
      {dimensions.map((d) => (
        <Row key={d.key + (d.extraction_id ?? '')} dimension={d} />
      ))}
    </AssessmentRowsFrame>
  )
}

/** The rows' bones: a name, a teaser line and a two-digit value each. */
export function AssessmentRowsSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <AssessmentRowsFrame state="skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <AssessmentRowFrame
          key={i}
          name={<Bone.Text widths={['11ch']} />}
          teaser={<Bone.Text widths={['88%', '76%', '92%', '70%', '84%'].slice(i % 5)} />}
          value={<Bone.Number digits={2} />}
        />
      ))}
    </AssessmentRowsFrame>
  )
}

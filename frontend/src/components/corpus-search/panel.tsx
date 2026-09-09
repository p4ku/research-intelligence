'use client'

import { MiniScore, screeningLabel } from '@/components/scanner-ui'
import { fmt, formatDate, formatNumber } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { PASSED_STATUSES } from '@/lib/papers/types'
import { highlight, type Segment } from '@/lib/search/match'
import {
  ArrowRightIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/16/solid'
import clsx from 'clsx'
import Link from 'next/link'
import type { MouseEvent, ReactNode } from 'react'
import { rowId, type Row, type Section } from './rows'

/**
 * The results, presentational: a listbox of grouped rows under the field.
 * Score-first on paper rows (MiniScore → title → author · domain · date),
 * hits in bold, a hairline between groups and nothing else. Stale results
 * stay visible and dim under `data-pending` — never bones.
 */

const PANEL =
  'border-line-strong bg-surface absolute inset-x-0 top-[calc(100%+0.375rem)] z-30 max-h-[min(28rem,50vh)] origin-top overflow-y-auto overscroll-contain rounded-sm border p-1.5 shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)] transition-opacity duration-150 data-pending:opacity-60 animate-rise-in motion-reduce:animate-none dark:border-line dark:shadow-none'

const ROW =
  'flex w-full min-w-0 items-center gap-3 rounded-sm px-2 py-2 text-left transition-colors duration-100 ease-out'

const LABEL =
  'text-muted-foreground px-2.5 pt-2 pb-1 font-mono text-[11px] font-medium tracking-[0.14em] uppercase'

/** Hit segments in bold — no colour, no highlighter yellow. */
export function Segments({ segments }: { segments: Segment[] }) {
  return (
    <>
      {segments.map((s, i) =>
        s.hit ? (
          <mark key={i} className="bg-transparent font-semibold text-inherit">
            {s.text}
          </mark>
        ) : (
          s.text
        ),
      )}
    </>
  )
}

function Body({ title, sub, extra }: { title: ReactNode; sub?: ReactNode; extra?: ReactNode }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[13px] font-medium text-foreground">{title}</span>
      {sub && (
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{sub}</span>
      )}
      {extra && (
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{extra}</span>
      )}
    </span>
  )
}

const Arrow = () => <ArrowRightIcon className="size-3 shrink-0 text-muted-foreground" />

function RowContent({
  row,
  tokens,
  showDomain,
}: {
  row: Row
  tokens: string[]
  showDomain: boolean
}) {
  const t = useT()
  const { lang } = useLanguage()
  switch (row.kind) {
    case 'paper': {
      const { hit } = row
      const passed = PASSED_STATUSES.includes(hit.screening_status)
      const sub = [
        hit.first_author,
        showDomain ? hit.workspace_name : null,
        formatDate(hit.created_at, lang),
        passed ? null : screeningLabel(hit.screening_status, t),
      ]
        .filter(Boolean)
        .join(' · ')
      const snippet = hit.matched.includes('abstract') ? highlight(hit.snippet, tokens) : null
      return (
        <>
          <MiniScore score={hit.signal_score} />
          <Body
            title={<Segments segments={highlight(hit.title, tokens)} />}
            sub={sub}
            extra={snippet?.some((s) => s.hit) ? <Segments segments={snippet} /> : undefined}
          />
        </>
      )
    }
    case 'more':
      return (
        <>
          <span className="min-w-0 flex-1 text-[13px] font-medium text-blue-700">
            {fmt(t('See all {n} papers'), { n: formatNumber(row.total, lang) })}
          </span>
          <Arrow />
        </>
      )
    case 'domain':
      return (
        <>
          <Body
            title={row.name}
            sub={fmt(t('{n} matching'), { n: formatNumber(row.matched, lang) })}
          />
          <Arrow />
        </>
      )
    case 'ask':
      return (
        <>
          <ChatBubbleLeftRightIcon className="size-4 shrink-0 text-blue-700" />
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-blue-700">
            {row.label}
          </span>
          <Arrow />
        </>
      )
    case 'papers':
      return (
        <>
          <span className="min-w-0 flex-1 text-[13px] font-medium text-blue-700">
            {t('Open Papers')}
          </span>
          <Arrow />
        </>
      )
    case 'recent':
      return (
        <>
          <ClockIcon className="size-4 shrink-0 text-zinc-400" />
          <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{row.q}</span>
        </>
      )
    case 'try':
      return (
        <>
          <MagnifyingGlassIcon className="size-4 shrink-0 text-zinc-400" />
          <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{row.q}</span>
        </>
      )
  }
}

export function SearchPanel({
  id,
  sections,
  cursor,
  pending,
  tokens,
  showDomain,
  onCursor,
  onActivate,
  onClearRecent,
}: {
  id: string
  sections: Section[]
  /** Index into the flattened rows; -1 = none. */
  cursor: number
  pending: boolean
  /** The query's tokens, for bolding hits. */
  tokens: string[]
  showDomain: boolean
  onCursor: (index: number) => void
  onActivate: (row: Row) => void
  onClearRecent: () => void
}) {
  const t = useT()
  // Each section's first row index in the flattened list (what `cursor` indexes).
  const starts: number[] = []
  let count = 0
  for (const section of sections) {
    starts.push(count)
    count += section.rows.length
  }
  const keepFocus = (e: MouseEvent) => e.preventDefault()

  return (
    <div
      id={id}
      role="listbox"
      aria-label={t('Search results')}
      data-pending={pending || undefined}
      className={PANEL}
    >
      {sections.map((section, s) => (
        <div
          key={section.key}
          role="group"
          aria-label={section.label ?? undefined}
          className={clsx(s > 0 && 'mt-1 border-t border-line-soft pt-1')}
        >
          {section.label && (
            <div className="flex items-baseline justify-between">
              <div className={LABEL}>{section.label}</div>
              {section.key === 'recent' && (
                <button
                  type="button"
                  tabIndex={-1}
                  onMouseDown={keepFocus}
                  onClick={onClearRecent}
                  className="px-2.5 text-[11px] text-muted-foreground hover:text-foreground"
                >
                  {t('Clear recent searches')}
                </button>
              )}
            </div>
          )}
          {section.note && (
            <p className="px-2.5 py-3 text-sm text-muted-foreground">{section.note}</p>
          )}
          {section.rows.map((row, r) => {
            const i = starts[s]! + r
            const selected = i === cursor
            const common = {
              id: rowId(row),
              role: 'option' as const,
              'aria-selected': selected,
              tabIndex: -1,
              onMouseDown: keepFocus,
              onMouseMove: () => {
                if (!selected) onCursor(i)
              },
              className: clsx(ROW, selected && 'bg-foreground/5'),
            }
            const content = <RowContent row={row} tokens={tokens} showDomain={showDomain} />
            return 'href' in row ? (
              <Link
                key={common.id}
                {...common}
                href={row.href}
                prefetch={false}
                onClick={(e) => {
                  // Plain clicks go through the field's transition; modified
                  // clicks (new tab) keep the link's own behaviour.
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
                  e.preventDefault()
                  onActivate(row)
                }}
              >
                {content}
              </Link>
            ) : (
              <button key={common.id} {...common} type="button" onClick={() => onActivate(row)}>
                {content}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

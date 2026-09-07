'use client'

import { MINI_SCORE, MiniScore } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { fmt, formatDate } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { useEffect, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import type { PaletteEntry } from './types'

function matches(entry: PaletteEntry, query: string): boolean {
  const q = query.toLowerCase()
  return (
    entry.title.toLowerCase().includes(q) ||
    (entry.first_author?.toLowerCase().includes(q) ?? false) ||
    entry.source.toLowerCase().includes(q) ||
    entry.id.includes(q)
  )
}

/** The rows on offer for a query: matches, or the top five by signal when empty. */
export function pickable(entries: PaletteEntry[], query: string): PaletteEntry[] {
  const q = query.trim()
  return q ? entries.filter((e) => matches(e, q)) : entries.slice(0, 5)
}

// MiniScore and scoreColor moved to scanner-ui so the Home search can share
// them; re-exported here for the console and the skeleton gallery.
export { MiniScore, scoreColor } from '@/components/scanner-ui'

/* ---------------------------------- Frame ---------------------------------- */

/** Below the composer on the empty page, above it once docked; `static` sits in flow (the gallery). */
export type PickerPlacement = 'below' | 'above' | 'static'

const ROW =
  'flex w-full items-center gap-3 rounded-sm px-2 py-2 text-left transition-colors duration-100 ease-out'

function PickerFrame({
  placement,
  state = 'loaded',
  footer,
  children,
  ...props
}: {
  placement: PickerPlacement
  state?: 'loaded' | 'skeleton'
  footer: ReactNode
  children: ReactNode
} & ComponentPropsWithoutRef<'div'>) {
  return (
    <div
      {...props}
      data-shape="paper-picker"
      data-state={state}
      className={clsx(
        'max-h-[min(19rem,38vh)] overflow-y-auto rounded-sm border border-line-strong bg-surface p-1.5 shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)]',
        placement !== 'static' &&
          'absolute inset-x-0 z-30 animate-rise-in motion-reduce:animate-none',
        placement === 'below' && 'top-[calc(100%-0.75rem)] origin-top',
        placement === 'above' && 'bottom-[calc(100%-0.375rem)] origin-bottom',
      )}
    >
      {children}
      <div className="mt-1 flex items-center gap-3 border-t border-line-soft px-2.5 pt-2 pb-0.5 text-[11px] text-muted-foreground">
        {footer}
      </div>
    </div>
  )
}

function RowBody({ score, title, sub }: { score: ReactNode; title: ReactNode; sub: ReactNode }) {
  return (
    <>
      {score}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium text-foreground">{title}</span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{sub}</span>
      </span>
    </>
  )
}

/* ---------------------------------- Loaded --------------------------------- */

/**
 * The inline paper picker: a listbox attached to the composer while no paper
 * is chosen (entries arrive pre-sorted by signal).
 */
export function PaperPicker({
  entries,
  query,
  cursor,
  placement,
  onCursor,
  onPick,
}: {
  entries: PaletteEntry[]
  query: string
  cursor: number
  placement: PickerPlacement
  onCursor: (i: number) => void
  onPick: (entry: PaletteEntry) => void
}) {
  const t = useT()
  const { lang } = useLanguage()
  const shown = pickable(entries, query)
  const hasQuery = query.trim() !== ''

  // Keyboard travel keeps the highlighted row in view.
  useEffect(() => {
    document
      .querySelector('#paper-picker [aria-selected="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  return (
    <PickerFrame
      id="paper-picker"
      role="listbox"
      aria-label={t('Papers')}
      placement={placement}
      footer={
        <>
          <span>
            <kbd className="font-mono">↑↓</kbd> {t('choose')}
          </span>
          <span>
            <kbd className="font-mono">↵</kbd> {t('scope the conversation')}
          </span>
          <span className="ml-auto tabular-nums">
            {hasQuery
              ? fmt(t('{n} of {total}'), { n: shown.length, total: entries.length })
              : fmt(t('Top {n} of {total}'), { n: shown.length, total: entries.length })}
          </span>
        </>
      }
    >
      {shown.length > 0 ? (
        shown.map((entry, i) => (
          <button
            key={entry.id}
            type="button"
            role="option"
            aria-selected={i === cursor}
            data-row="pick"
            onMouseEnter={() => onCursor(i)}
            // Keep the caret in the composer.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onPick(entry)}
            className={clsx(ROW, i === cursor && 'bg-foreground/5')}
          >
            <RowBody
              score={<MiniScore score={entry.signal_score} />}
              title={entry.title}
              sub={[entry.first_author, entry.source, formatDate(entry.created_at, lang)]
                .filter(Boolean)
                .join(' · ')}
            />
          </button>
        ))
      ) : (
        <p className="px-3 py-6 text-center text-sm text-muted-foreground">
          {fmt(t('No papers match “{q}” — {n} papers to choose from.'), {
            q: query.trim(),
            n: entries.length,
          })}
        </p>
      )}
    </PickerFrame>
  )
}

/* --------------------------------- Skeleton -------------------------------- */

const TITLE_WIDTHS = [['62%'], ['46%'], ['74%']]

/**
 * The picker's bones — for loading.tsx and the gallery only. The live picker
 * is client state and never blocks first paint, so this never replaces it.
 */
export function PaperPickerSkeleton({
  rows = 5,
  placement = 'static',
}: {
  rows?: number
  placement?: PickerPlacement
}) {
  const t = useT()
  return (
    <PickerFrame
      placement={placement}
      state="skeleton"
      footer={
        <>
          <span>
            <kbd className="font-mono">↑↓</kbd> {t('choose')}
          </span>
          <span>
            <kbd className="font-mono">↵</kbd> {t('scope the conversation')}
          </span>
          <span className="ml-auto tabular-nums">
            <Bone.Text widths={['11ch']} />
          </span>
        </>
      }
    >
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} data-row="pick" className={ROW}>
          <RowBody
            score={
              <span className={MINI_SCORE}>
                <Bone.Dot size={6} />
                <Bone.Number digits={2} />
              </span>
            }
            title={<Bone.Text widths={TITLE_WIDTHS[i % TITLE_WIDTHS.length]} />}
            sub={<Bone.Text widths={['26ch']} />}
          />
        </div>
      ))}
    </PickerFrame>
  )
}

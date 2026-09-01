'use client'

import { fmt, formatDate } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { useEffect } from 'react'
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

/** The threshold colour a score reads in: accent, warn, or neutral. */
export function scoreColor(score: number | null): string {
  if (score === null) return '#9a9a90'
  const rounded = Math.round(score)
  return rounded >= 75 ? 'var(--accent)' : rounded >= 55 ? 'var(--warn)' : '#9a9a90'
}

/** Compact score for tight spots: threshold dot + tabular number. */
export function MiniScore({ score }: { score: number | null }) {
  if (score === null) return null
  return (
    <span className="text-foreground/80 flex shrink-0 items-center gap-1 font-mono text-xs font-medium tabular-nums">
      <span className="size-1.5 rounded-full" style={{ backgroundColor: scoreColor(score) }} />
      {Math.round(score)}
    </span>
  )
}

/**
 * The inline paper picker: a listbox attached to the composer while no paper
 * is chosen (entries arrive pre-sorted by signal). Below the composer on the
 * empty page, above it once the composer has docked.
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
  placement: 'below' | 'above'
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
    <div
      id="paper-picker"
      role="listbox"
      aria-label={t('Papers')}
      className={clsx(
        'border-line-strong bg-surface absolute inset-x-0 z-30 max-h-[min(19rem,38vh)] overflow-y-auto rounded-sm border p-1.5 shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)]',
        'animate-rise-in motion-reduce:animate-none',
        placement === 'below'
          ? 'top-[calc(100%-0.75rem)] origin-top'
          : 'bottom-[calc(100%-0.375rem)] origin-bottom',
      )}
    >
      {shown.length > 0 ? (
        shown.map((entry, i) => (
          <button
            key={entry.id}
            type="button"
            role="option"
            aria-selected={i === cursor}
            onMouseEnter={() => onCursor(i)}
            // Keep the caret in the composer.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onPick(entry)}
            className={clsx(
              'flex w-full items-center gap-3 rounded-sm px-2 py-2 text-left transition-colors duration-100 ease-out',
              i === cursor && 'bg-foreground/5',
            )}
          >
            <MiniScore score={entry.signal_score} />
            <span className="min-w-0 flex-1">
              <span className="text-foreground block truncate text-[13px] font-medium">
                {entry.title}
              </span>
              <span className="text-muted-foreground mt-0.5 block truncate text-[11px]">
                {[entry.first_author, entry.source, formatDate(entry.created_at, lang)]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </span>
          </button>
        ))
      ) : (
        <p className="text-muted-foreground px-3 py-6 text-center text-sm">
          {fmt(t('No papers match “{q}” — the workspace holds {n} papers.'), {
            q: query.trim(),
            n: entries.length,
          })}
        </p>
      )}

      <div className="border-line-soft text-muted-foreground mt-1 flex items-center gap-3 border-t px-2.5 pt-2 pb-0.5 text-[11px]">
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
      </div>
    </div>
  )
}

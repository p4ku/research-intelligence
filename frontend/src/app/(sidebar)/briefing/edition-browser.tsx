'use client'

import { SignalScore } from '@/components/scanner-ui'
import { fmt, type Lang } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/20/solid'
import clsx from 'clsx'
import Link from 'next/link'
import { useMemo, useRef, useState } from 'react'
import { formatEditionDate } from './format'

export interface BrowserEdition {
  date: string
  title: string
  inBrief: string
  /** 'template' until the backend's reporting step writes model prose. */
  proseSource: 'model' | 'template'
  funnel: { screened: number; included: number; inBriefing: number }
  papers: { id: string; title: string; signal: number | null }[]
}

/**
 * The archive as a reading room, as on the previous Briefings page: search
 * spans the top, the selected brief reads on the left two-thirds, and the
 * edition history is the sticky right rail.
 */
export function EditionBrowser({ editions, lang }: { editions: BrowserEdition[]; lang: Lang }) {
  const t = useT()
  const searchRef = useRef<HTMLInputElement>(null)
  const readerRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [activeDate, setActiveDate] = useState(editions[0]?.date)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return editions
    return editions.filter((e) =>
      [e.title, e.inBrief, ...e.papers.map((p) => p.title)].join(' ').toLowerCase().includes(q),
    )
  }, [editions, query])

  // Keep the reader on a still-visible edition when a search narrows the list.
  const active =
    filtered.find((e) => e.date === activeDate) ??
    editions.find((e) => e.date === activeDate) ??
    filtered[0] ??
    null

  function select(date: string) {
    setActiveDate(date)
    // Only nudge the reader into view on the stacked (mobile) layout.
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      readerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <div className="space-y-6">
      {/* --- Search spans the full width above both panes, as on Papers. --- */}
      <div className="group focus-within:border-accent/60 focus-within:ring-accent/15 border-line bg-surface relative flex items-center gap-3 rounded-md border px-4 py-3 transition focus-within:ring-4">
        <MagnifyingGlassIcon className="group-focus-within:text-accent size-5 shrink-0 text-zinc-400 transition-colors" />
        <input
          ref={searchRef}
          name="search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setQuery('')
              searchRef.current?.blur()
            }
          }}
          placeholder={t('Search briefings by subject, summary, or paper…')}
          aria-label={t('Search the digest archive')}
          className="min-w-0 flex-1 bg-transparent text-base text-zinc-950 placeholder:text-zinc-400 focus:outline-none dark:text-white [&::-webkit-search-cancel-button]:hidden"
        />
        {query !== '' && (
          <>
            <span className="shrink-0 font-mono text-xs text-zinc-400 tabular-nums">
              {fmt(t('{n} hits'), { n: filtered.length })}
            </span>
            <button
              type="button"
              onClick={() => {
                setQuery('')
                searchRef.current?.focus()
              }}
              aria-label={t('Clear search')}
              className="shrink-0 rounded-md p-1 text-zinc-400 hover:bg-zinc-950/5 hover:text-zinc-950 dark:hover:bg-white/10 dark:hover:text-white"
            >
              <XMarkIcon className="size-4" />
            </button>
          </>
        )}
      </div>

      {/* Same grid as Papers/Ask: the reader spans 2/3, history is the right 1/3. */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* -------------------------------- Reader ------------------------------- */}
        <div ref={readerRef} className="scroll-mt-24 lg:col-span-2">
          {active ? (
            <article className="border-line-soft rounded-2xl border bg-white p-6 shadow-xs sm:p-8 dark:bg-zinc-900/40">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <div className="flex items-baseline gap-2 font-mono text-[11px] tracking-[0.14em] text-zinc-400 uppercase dark:text-zinc-500">
                  {formatEditionDate(active.date, lang)}
                  {active.proseSource === 'template' && (
                    <span className="border-line rounded-sm border px-1 py-px normal-case">
                      {t('auto-brief')}
                    </span>
                  )}
                </div>
                <Link
                  href={`/briefing/${active.date}`}
                  className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {t('Open briefing →')}
                </Link>
              </div>
              <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-zinc-950 dark:text-white">
                {active.title}
              </h2>
              <p className="mt-2 font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                {fmt(
                  t('{screened} screened → {included} included → {inBriefing} in the briefing'),
                  {
                    screened: active.funnel.screened,
                    included: active.funnel.included,
                    inBriefing: active.funnel.inBriefing,
                  },
                )}
              </p>

              <p className="mt-5 max-w-2xl text-sm leading-relaxed text-pretty text-zinc-600 dark:text-zinc-300">
                {active.inBrief}
              </p>

              <div className="border-line-soft mt-6 border-t pt-5">
                <div className="font-mono text-[11px] font-medium tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
                  {active.papers.length === 1
                    ? t('1 paper')
                    : fmt(t('{n} papers'), { n: active.papers.length })}
                </div>
                <ol className="mt-3 space-y-3">
                  {active.papers.map((p) => (
                    <li key={p.id} className="flex items-center gap-3">
                      <SignalScore score={p.signal} size="sm" />
                      <Link
                        href={`/papers/${p.id}`}
                        className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-800 hover:underline dark:text-zinc-100"
                      >
                        {p.title}
                      </Link>
                    </li>
                  ))}
                </ol>
              </div>
            </article>
          ) : (
            <div className="border-line rounded-sm border border-dashed p-10 text-center text-sm text-zinc-400">
              {t('No briefings match your search.')}
            </div>
          )}
        </div>

        {/* ---- History: above the reader on mobile, the right 1/3 on desktop ---- */}
        <nav
          aria-label={t('Briefing history')}
          className="max-lg:order-first lg:sticky lg:top-24 lg:col-span-1 lg:self-start"
        >
          <p className="px-1 font-mono text-[11px] tracking-wide text-zinc-400 tabular-nums dark:text-zinc-500">
            {fmt(t('{n} of {total} briefings'), { n: filtered.length, total: editions.length })}
          </p>
          <ul className="-mx-1 mt-2 max-h-[70vh] space-y-0.5 overflow-y-auto pr-1 lg:pb-4">
            {filtered.map((e) => {
              const current = active?.date === e.date
              const isToday = e.date === editions[0]?.date
              return (
                <li key={e.date}>
                  <button
                    type="button"
                    onClick={() => select(e.date)}
                    aria-current={current ? 'true' : undefined}
                    className={clsx(
                      'group relative block w-full rounded-lg py-3 pr-3 pl-4 text-left transition-colors',
                      current
                        ? 'bg-zinc-950/[0.04] dark:bg-white/[0.06]'
                        : 'hover:bg-zinc-950/[0.025] dark:hover:bg-white/[0.03]',
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={clsx(
                        'absolute top-3 bottom-3 left-0 w-0.5 rounded-full transition-colors',
                        current
                          ? 'bg-accent'
                          : 'bg-transparent group-hover:bg-zinc-300 dark:group-hover:bg-zinc-600',
                      )}
                    />
                    <div
                      className={clsx(
                        'font-mono text-[11px] tracking-wide tabular-nums',
                        current
                          ? 'text-zinc-700 dark:text-zinc-200'
                          : 'text-zinc-400 dark:text-zinc-500',
                      )}
                    >
                      {formatEditionDate(e.date, lang)}
                      {isToday && <span className="text-accent ml-2">{t('Today')}</span>}
                    </div>
                    <p
                      className={clsx(
                        'mt-1 line-clamp-2 text-sm leading-snug',
                        current
                          ? 'font-medium text-zinc-950 dark:text-white'
                          : 'text-zinc-600 group-hover:text-zinc-900 dark:text-zinc-300 dark:group-hover:text-white',
                      )}
                    >
                      {e.title}
                    </p>
                  </button>
                </li>
              )
            })}
            {filtered.length === 0 && (
              <li className="border-line rounded-lg border border-dashed px-4 py-8 text-center text-sm text-zinc-400 dark:text-zinc-500">
                {t('No briefings match your search.')}
              </li>
            )}
          </ul>
        </nav>
      </div>
    </div>
  )
}

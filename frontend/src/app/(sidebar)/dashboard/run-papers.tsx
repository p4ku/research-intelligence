'use client'

import { PageNav } from '@/components/page-nav'
import { PaperCard } from '@/components/paper-card'
import { useT } from '@/lib/i18n-client'
import { byValueDesc, dimensionByKey, numericDefinitions } from '@/lib/papers/select'
import type { ScoredPaper, WorkspaceSummary } from '@/lib/papers/types'
import { ChevronDownIcon, SignalIcon, SparklesIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'

const PER_PAGE = 5

/** 'overall' | a definition key */
type Sort = string

/**
 * The run's surfaced papers — the dashboard's "all the papers" list. A single
 * run is small, so the only control is sort (a tab strip on desktop, a select
 * on mobile); the list paginates five at a time. "Overall score" is the
 * backend's composite signal score; the other tabs are the workspace's own
 * scored definitions.
 */
export function RunPapers({
  papers,
  workspace,
}: {
  papers: ScoredPaper[]
  workspace: WorkspaceSummary
}) {
  const t = useT()
  const [sort, setSort] = useState<Sort>('overall')
  const [page, setPage] = useState(1)

  const sortTabs = useMemo(
    () => [
      { id: 'overall', label: t('Overall score'), icon: SignalIcon },
      ...numericDefinitions(workspace, papers)
        .filter((d) => !d.is_trl)
        .map((d) => ({ id: d.key, label: d.name, icon: SparklesIcon })),
    ],
    [workspace, papers, t],
  )

  const sorted = useMemo(
    () =>
      papers
        .slice()
        .sort((a, b) =>
          sort === 'overall'
            ? byValueDesc(a.signal_score, b.signal_score)
            : byValueDesc(
                dimensionByKey(a, sort)?.value ?? null,
                dimensionByKey(b, sort)?.value ?? null,
              ),
        ),
    [papers, sort],
  )

  // Paginate, five at a time. Reset to the first page whenever the sort changes
  // so the view never lands past the end.
  const pageCount = Math.max(1, Math.ceil(sorted.length / PER_PAGE))
  useEffect(() => {
    setPage(1)
  }, [sort])
  const current = Math.min(page, pageCount)
  const start = (current - 1) * PER_PAGE
  const paged = sorted.slice(start, start + PER_PAGE)

  return (
    <div className="space-y-4">
      {/* Sort on the left (tabs on desktop, a select on mobile), count on the right. */}
      <div className="border-line-soft flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b">
        {/* Mobile: a select. */}
        <div className="relative grid w-full grid-cols-1 pb-3 sm:hidden">
          <label htmlFor="run-sort" className="sr-only">
            {t('Sort by')}
          </label>
          <select
            id="run-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="border-line bg-surface col-start-1 row-start-1 w-full appearance-none rounded-sm border py-1.5 pr-8 pl-3 text-sm text-zinc-950 focus:outline-2 focus:-outline-offset-2 focus:outline-[var(--accent)] dark:text-white"
          >
            {sortTabs.map((s) => (
              <option key={s.id} value={s.id}>
                {t('Sort')}: {s.label}
              </option>
            ))}
          </select>
          <ChevronDownIcon
            aria-hidden="true"
            className="pointer-events-none col-start-1 row-start-1 mt-0.5 mr-2.5 size-4 self-center justify-self-end text-zinc-400"
          />
        </div>

        {/* Desktop: underline tabs with icons. */}
        <nav aria-label={t('Sort by')} className="-mb-px hidden items-center gap-6 sm:flex">
          {sortTabs.map((s) => {
            const active = sort === s.id
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setSort(s.id)}
                aria-current={active ? 'true' : undefined}
                className={clsx(
                  'group inline-flex items-center border-b-2 pt-1 pb-2.5 text-sm font-medium transition-colors',
                  active
                    ? 'border-accent text-zinc-950 dark:text-white'
                    : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-950 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:text-white',
                )}
              >
                <s.icon
                  aria-hidden="true"
                  className={clsx(
                    'mr-1.5 -ml-0.5 size-4',
                    active
                      ? 'text-accent'
                      : 'text-zinc-400 group-hover:text-zinc-500 dark:text-zinc-500 dark:group-hover:text-zinc-400',
                  )}
                />
                {s.label}
              </button>
            )
          })}
        </nav>
        <p className="pb-3 text-sm text-zinc-500 tabular-nums sm:pb-0 dark:text-zinc-400">
          <span className="font-mono font-medium text-zinc-950 dark:text-white">
            {sorted.length}
          </span>{' '}
          {sorted.length === 1 ? t('paper') : t('papers')}
        </p>
      </div>

      <div className="space-y-3">
        {paged.map((p) => (
          <PaperCard key={p.id} paper={p} />
        ))}
        {sorted.length === 0 && (
          <div className="border-line rounded-sm border border-dashed p-10 text-center text-sm text-zinc-400">
            {t('No papers in this run.')}
          </div>
        )}
      </div>

      <PageNav
        page={current}
        pageCount={pageCount}
        onChange={setPage}
        className="pt-1"
        labels={{ prev: t('Previous'), next: t('Next') }}
      />
    </div>
  )
}

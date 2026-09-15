'use client'

import { FilterGroup, MinScoreSlider, OptionButton } from '@/components/filter-rail'
import { PageNav } from '@/components/page-nav'
import { PaperCard } from '@/components/paper-card'
import { SectionLabel } from '@/components/scanner-ui'
import { StarredChip } from '@/components/star'
import { useFeatures } from '@/lib/features-client'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { paperHref } from '@/lib/papers/href'
import type { ScoredPaper } from '@/lib/papers/types'
import { useStars } from '@/lib/stars-client'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useRef, useState } from 'react'
import {
  applyView,
  DEFAULT_VIEW,
  isDefaultView,
  PAGE_SIZE,
  pageOf,
  SCORE_CEILING,
  SCORE_STEP,
  searchWith,
  sortOptions,
  viewFrom,
  withKnownSort,
  type EditionView,
} from './view'

function useSafeRouter() {
  try {
    return useRouter()
  } catch {
    return null
  }
}

/**
 * The edition's papers, with the rail that orders and narrows them (the
 * white paper's SORT BY / SIGNAL STRENGTH box) and the Starred filter.
 * Client-side because the filter reads the star store and the view is
 * applied in hand — a briefing is one run's list, so no fetch is needed.
 * The header row and the rail mirror EditionPapersSkeleton (skeletons.tsx)
 * slot for slot. Each card links to the paper *as this run read it*
 * (`?run=`), so the page opens on the score and decision the card shows
 * rather than a later run's.
 *
 * The URL is the view: `?sort=`, `?score=` and `?page=` are read afresh every
 * render (never seeded from a prop — the App Router serves a Back from its
 * cache without a server render), and written with `replaceState` beside the
 * briefing's own `domain` and `run`. The gallery keeps local state via
 * `syncUrl={false}`.
 *
 * The list is cut into pages of PAGE_SIZE after the sort and the floor, so
 * a large briefing (566 papers on prod) mounts twenty cards, not hundreds;
 * a change of sort or floor starts again from the first page.
 */
export function EditionPaperList({
  papers,
  runId,
  logHref,
  syncUrl = true,
  total,
  page: _serverPage,
  pageSize = PAGE_SIZE,
}: {
  papers: ScoredPaper[]
  /** The edition's run — the reading its cards show. */
  runId: string
  logHref: string
  syncUrl?: boolean
  total?: number
  page?: number
  pageSize?: number
}) {
  const t = useT()
  const { isStarred } = useStars()
  const { stars } = useFeatures()
  const [starredOnly, setStarredOnly] = useState(false)
  // Null outside the App Router (a static test render, the gallery).
  const params = useSearchParams()
  const router = useSafeRouter()
  const [local, setLocal] = useState<EditionView>(DEFAULT_VIEW)
  const asked = syncUrl && params ? viewFrom(Object.fromEntries(params)) : local
  const update = useCallback(
    (patch: Partial<EditionView>) => {
      // A narrower or reordered list starts again from its first page: page
      // three of one order is no place in another.
      const change = 'page' in patch ? patch : { ...patch, page: 1 }
      if (!syncUrl) {
        setLocal((v) => ({ ...v, ...change }))
        return
      }
      // From the address bar as it is now, so two writes inside one render
      // build on each other and the briefing's own params survive.
      const current = new URLSearchParams(window.location.search)
      const next = { ...viewFrom(Object.fromEntries(current)), ...change }
      const newQuery = searchWith(current.toString(), next)
      const newPath = window.location.pathname + newQuery

      if (total !== undefined && 'page' in patch) {
        if (router) {
          router.push(newPath)
        } else if (typeof window !== 'undefined') {
          window.location.assign(newPath)
        }
      } else {
        // No navigation: the App Router picks the query up from history and
        // `useSearchParams` re-renders.
        window.history.replaceState(null, '', newPath)
      }
    },
    [syncUrl, total, router],
  )

  // The pager sits under the last card, so a turned page would open at its
  // foot: the section is brought back to the top of the viewport instead.
  // Instant, not smooth — the cards have already changed under the reader.
  const top = useRef<HTMLElement>(null)
  const turnTo = useCallback(
    (page: number) => {
      update({ page })
      top.current?.scrollIntoView({ block: 'start', behavior: 'instant' })
    },
    [update],
  )

  const starred = papers.filter((p) => isStarred('paper', p.id))
  // The effective filter, not the state: with the chip gone there would be no
  // way to clear it, so a flip taken mid-filter must show the whole edition.
  const filtering = stars && starredOnly
  const sorts = sortOptions(papers, t)
  // The effective view, like the effective filter: a sort the rail cannot
  // offer is the score's.
  const view = withKnownSort(asked, sorts)
  const shown = applyView(filtering ? starred : papers, view)

  const isServerPaged = total !== undefined
  const totalPapers = total ?? shown.length
  const paged = pageOf(shown, view.page, pageSize)
  const pageCount = isServerPaged ? Math.max(1, Math.ceil(totalPapers / pageSize)) : paged.pageCount
  const currentPage = isServerPaged ? view.page : paged.page
  const from = isServerPaged
    ? totalPapers === 0
      ? 0
      : (currentPage - 1) * pageSize + 1
    : paged.from
  const to = isServerPaged
    ? Math.min(totalPapers, (currentPage - 1) * pageSize + papers.length)
    : paged.to
  const cardsToRender = isServerPaged ? shown : paged.rows

  const narrowed = view.minScore > 0
  const sortLabel = sorts.find((s) => s.id === view.sort)?.label ?? sorts[0]!.label

  return (
    <section ref={top} className="scroll-mt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel size="sm">{t('The papers')}</SectionLabel>
        <span className="flex flex-wrap items-baseline justify-end gap-x-4 gap-y-1">
          <span className="font-mono text-[11px] whitespace-nowrap text-zinc-400 tabular-nums dark:text-zinc-500">
            {pageCount > 1
              ? fmt(t('{from}–{to} of {n} papers'), {
                  from,
                  to,
                  n: totalPapers,
                })
              : totalPapers === 1
                ? t('1 paper')
                : fmt(t('{n} papers'), { n: totalPapers })}
          </span>
          {stars && (
            <StarredChip
              active={starredOnly}
              count={starred.length}
              onToggle={() => setStarredOnly((v) => !v)}
            />
          )}
          {(!isDefaultView(view) || filtering) && (
            <button
              type="button"
              onClick={() => {
                update(DEFAULT_VIEW)
                setStarredOnly(false)
              }}
              className="text-xs font-medium whitespace-nowrap text-zinc-600 hover:text-zinc-950 dark:text-zinc-300 dark:hover:text-white"
            >
              {t('Reset filters')}
            </button>
          )}
          <Link
            href={logHref}
            className="text-xs font-medium whitespace-nowrap text-blue-600 hover:underline dark:text-blue-400"
          >
            {t('Screening log →')}
          </Link>
        </span>
      </div>
      <div className="mt-5 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="space-y-3">
            {cardsToRender.map((p) => (
              <PaperCard key={p.id} paper={p} href={paperHref(p.id, { runId })} />
            ))}
            {shown.length === 0 && (
              <div className="rounded-sm border border-dashed border-line p-10 text-center text-sm text-zinc-400">
                {filtering && starred.length === 0
                  ? t('Nothing starred yet.')
                  : narrowed
                    ? t('No papers match these filters.')
                    : t('No papers are on file for this briefing.')}
              </div>
            )}
          </div>
          {/* Renders nothing for a single page, so a small briefing is unchanged. */}
          <PageNav
            page={currentPage}
            pageCount={pageCount}
            onChange={turnTo}
            className="mt-6"
            labels={{ prev: t('Previous'), next: t('Next') }}
          />
        </div>

        {/* The view's controls: below the cards on a phone, at their right on a desk. */}
        <aside className="divide-y divide-line lg:col-span-1">
          <FilterGroup label={t('Sort by')} value={sortLabel}>
            <div className="space-y-1">
              {sorts.map((s) => (
                <OptionButton
                  key={s.id}
                  active={view.sort === s.id}
                  onClick={() => update({ sort: s.id })}
                  label={s.label}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup label={t('Total Score')} value={narrowed ? `≥ ${view.minScore}` : undefined}>
            <MinScoreSlider
              value={view.minScore}
              ceiling={SCORE_CEILING}
              step={SCORE_STEP}
              onChange={(minScore) => update({ minScore })}
              labels={{
                minimum: t('Minimum score'),
                low: t('Any score'),
                high: t('Only the strongest'),
              }}
            />
          </FilterGroup>
        </aside>
      </div>
    </section>
  )
}

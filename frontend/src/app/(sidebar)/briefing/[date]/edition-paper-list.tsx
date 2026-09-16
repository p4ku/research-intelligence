'use client'

import { FilterGroup, MinScoreSlider, OptionButton } from '@/components/filter-rail'
import { PageNav } from '@/components/page-nav'
import { PaperCard } from '@/components/paper-card'
import { SectionLabel } from '@/components/scanner-ui'
import { StarredChip } from '@/components/star'
import { Spinner } from '@/components/ui/spinner'
import { useFeatures } from '@/lib/features-client'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { paperHref } from '@/lib/papers/href'
import type { ScoredPaper } from '@/lib/papers/types'
import { useStars } from '@/lib/stars-client'
import clsx from 'clsx'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from 'react'
import {
  applyView,
  DEFAULT_VIEW,
  discoverNumericDimensions,
  isDefaultView,
  PAGE_SIZE,
  pageOf,
  SCORE_CEILING,
  SCORE_STEP,
  searchWith,
  sortOptions,
  viewFrom,
  withKnownSort,
  type DefinitionMeta,
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
 * When server pagination is enabled (`total !== undefined`), filtering by score
 * and sorting are executed globally on the server across the database dataset.
 * When client-side, the list derives every render from `useSearchParams`.
 */
export function EditionPaperList({
  papers,
  runId,
  logHref,
  syncUrl = true,
  total,
  page: serverPage,
  pageSize = PAGE_SIZE,
  definitions,
  initialView,
}: {
  papers: ScoredPaper[]
  /** The edition's run — the reading its cards show. */
  runId: string
  logHref: string
  syncUrl?: boolean
  total?: number
  page?: number
  pageSize?: number
  definitions?: readonly DefinitionMeta[]
  initialView?: EditionView
}) {
  const t = useT()
  const { isStarred } = useStars()
  const { stars } = useFeatures()
  const [starredOnly, setStarredOnly] = useState(false)
  // Null outside the App Router (a static test render, the gallery).
  const params = useSearchParams()
  const router = useSafeRouter()
  const [local, setLocal] = useState<EditionView>(
    initialView ?? (serverPage ? { ...DEFAULT_VIEW, page: serverPage } : DEFAULT_VIEW),
  )
  const [isPending, startTransition] = useTransition()
  const [targetPage, setTargetPage] = useState<number | null>(null)
  const prevPageRef = useRef<number | null>(null)

  const parsedParams = params ? viewFrom(Object.fromEntries(params)) : null
  const asked =
    syncUrl && parsedParams
      ? {
          ...parsedParams,
          ...(params?.get('page') ? {} : serverPage ? { page: serverPage } : {}),
        }
      : initialView
        ? { ...initialView, ...(serverPage ? { page: serverPage } : {}) }
        : { ...local, ...(serverPage ? { page: serverPage } : {}) }
  const update = useCallback(
    (patch: Partial<EditionView>) => {
      // A narrower or reordered list starts again from its first page: page
      // three of one order is no place in another.
      const change = 'page' in patch ? patch : { ...patch, page: 1 }
      if (!syncUrl) {
        setLocal((v) => ({ ...v, ...change }))
        return
      }
      if ('page' in patch) {
        setTargetPage(patch.page ?? 1)
      } else {
        setTargetPage(null)
      }
      // From the address bar as it is now, so two writes inside one render
      // build on each other and the briefing's own params survive.
      const current = new URLSearchParams(window.location.search)
      const next = { ...viewFrom(Object.fromEntries(current)), ...change }
      const newQuery = searchWith(current.toString(), next)
      const newPath = window.location.pathname + newQuery

      if (total !== undefined) {
        if (router) {
          startTransition(() => {
            router.push(newPath)
          })
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

  // The pager sits under the last card, so a turned page opens back at the
  // top of the viewport once loaded.
  const top = useRef<HTMLElement>(null)
  const turnTo = useCallback(
    (page: number) => {
      setTargetPage(page)
      startTransition(() => {
        update({ page })
      })
    },
    [update],
  )

  const starred = papers.filter((p) => isStarred('paper', p.id))
  // The effective filter, not the state: with the chip gone there would be no
  // way to clear it, so a flip taken mid-filter must show the whole edition.
  const filtering = stars && starredOnly
  const numericDimensions = useMemo(
    () => discoverNumericDimensions(papers, t, definitions),
    [definitions, papers, t],
  )
  const sorts = useMemo(() => sortOptions(papers, t, definitions), [definitions, papers, t])
  // The effective view, like the effective filter: a sort the rail cannot
  // offer is the score's.
  const view = withKnownSort(asked, sorts)
  const isServerPaged = total !== undefined
  const shown = isServerPaged
    ? filtering
      ? starred
      : papers
    : applyView(filtering ? starred : papers, view)

  const totalPapers = isServerPaged
    ? filtering
      ? starred.length
      : (total ?? papers.length)
    : shown.length
  const paged = pageOf(shown, view.page, pageSize)
  const pageCount = isServerPaged ? Math.max(1, Math.ceil(totalPapers / pageSize)) : paged.pageCount
  const currentPage = isServerPaged ? view.page : paged.page
  const pendingPage = isPending ? targetPage : null

  useEffect(() => {
    if (prevPageRef.current !== null && prevPageRef.current !== currentPage) {
      top.current?.scrollIntoView({ block: 'start', behavior: 'instant' })
    }
    prevPageRef.current = currentPage
  }, [currentPage])

  const from = isServerPaged
    ? totalPapers === 0
      ? 0
      : (currentPage - 1) * pageSize + 1
    : paged.from
  const to = isServerPaged
    ? Math.min(totalPapers, (currentPage - 1) * pageSize + shown.length)
    : paged.to
  const cardsToRender = isServerPaged ? shown : paged.rows

  const hasActiveDimFilter = Boolean(
    view.dimensionFilters && Object.values(view.dimensionFilters).some((v) => v > 0),
  )
  const narrowed = view.minScore > 0 || hasActiveDimFilter
  const sortLabel = sorts.find((s) => s.id === view.sort)?.label ?? sorts[0]!.label

  return (
    <section ref={top} className="scroll-mt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex items-center gap-3">
          <SectionLabel size="sm">{t('The papers')}</SectionLabel>
          {isPending && (
            <span className="inline-flex animate-pulse items-center gap-1.5 font-mono text-[11px] font-medium text-accent">
              <Spinner className="size-3 text-accent" />
              <span>
                {pendingPage ? fmt(t('Loading page {n}…'), { n: pendingPage }) : t('Loading…')}
              </span>
            </span>
          )}
        </div>
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
          {isPending && (
            <div className="mb-3 h-1 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div className="h-full w-2/5 animate-pulse rounded-full bg-accent" />
            </div>
          )}
          <div
            className={clsx(
              'space-y-3 transition-opacity duration-200',
              isPending && 'pointer-events-none opacity-40',
            )}
            aria-busy={isPending || undefined}
          >
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
            pendingPage={pendingPage}
            disabled={isPending}
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

          <FilterGroup
            label={t('Total Score')}
            value={view.minScore > 0 ? `≥ ${view.minScore}` : undefined}
          >
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

          {numericDimensions.map((dim) => {
            const currentVal = view.dimensionFilters?.[dim.key] ?? 0
            return (
              <FilterGroup
                key={dim.key}
                label={dim.label}
                value={currentVal > 0 ? `≥ ${currentVal}` : undefined}
              >
                <MinScoreSlider
                  value={currentVal}
                  ceiling={dim.max}
                  step={dim.step}
                  onChange={(val) => {
                    const nextDims = { ...(view.dimensionFilters ?? {}) }
                    if (val > 0) {
                      nextDims[dim.key] = val
                    } else {
                      delete nextDims[dim.key]
                    }
                    update({ dimensionFilters: nextDims })
                  }}
                  labels={{
                    minimum: t('Minimum score'),
                    low: '0',
                    high: String(dim.max),
                  }}
                />
              </FilterGroup>
            )
          })}
        </aside>
      </div>
    </section>
  )
}

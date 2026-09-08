'use client'

import { PageNav } from '@/components/page-nav'
import { PaperCard } from '@/components/paper-card'
import { SectionLabel } from '@/components/scanner-ui'
import { SearchFrame } from '@/components/search-frame'
import { StarredChip } from '@/components/star'
import { bffFetch } from '@/lib/bff/client'
import type { PapersList } from '@/lib/bff/papers/schema'
import { useFeatures } from '@/lib/features-client'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import {
  DEFAULT_STATE,
  keyOf,
  listPath,
  PER_PAGE,
  searchOf,
  stateFrom,
  type BrowseState,
  type Screening,
} from '@/lib/papers/browse'
import { useStars } from '@/lib/stars-client'
import { ChevronDownIcon, XMarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

/** 'signal' | 'recent' | 'dim:<definition key>' */
type Sort = string

const screeningOptions: { id: Screening; label: string }[] = [
  { id: 'passed', label: 'Passed' },
  { id: 'borderline', label: 'Borderline' },
  { id: 'pending', label: 'Pending' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'withdrawn', label: 'Withdrawn' },
  { id: 'all', label: 'All statuses' },
]

// Recent-time windows count back from the newest paper's ingest time (not
// wall-clock now), so "Last 24 hours" resolves to the freshest drop even in
// a corpus that hasn't been refreshed today. The BFF applies the rule.
const ingestedWindows = [
  { days: 1, label: 'Last 24 hours' },
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'This quarter' },
  { days: 0, label: 'All time' },
]

/** What the server rendered: the state it read from the URL and the page it answered with. */
export interface ServedPapers {
  state: BrowseState
  list: PapersList
}

/** A keystroke settles into the URL after this; chips and the pager write at once. */
const SEARCH_DEBOUNCE_MS = 150
/** A star toggle writes twice (optimistic, then settled); one refetch covers both. */
const STARS_SETTLE_MS = 250

/**
 * The papers browser. The URL is the state — every filter, the sort, the
 * search and the page — read afresh on every render, so Back/Forward, a
 * reload and Home's `?q=` all land on the same view. The server answered
 * the first page; every change after that is a fetch of `/bff/papers` for
 * one page plus the rail's facets, with the stale list dimmed under
 * `data-pending` meanwhile (never bones after the first paint). The rail
 * reads the facets, so it describes the whole corpus while the column
 * holds eight papers of it.
 */
export function PapersBrowser({
  served,
  domains,
}: {
  served: ServedPapers
  /** The domains the corpus spans; the filter shows when there is more than one. */
  domains: { id: string; name: string }[]
}) {
  const t = useT()
  const { stars: starSet } = useStars()
  const { stars } = useFeatures()
  const params = useSearchParams()
  const urlState = stateFrom(Object.fromEntries(params), domains)
  // The effective filter, not the URL's: a reader who flips stars off with the
  // chip engaged must see the whole corpus back, not a list silently narrowed
  // by a control that is no longer on screen. The server forces the same.
  const state: BrowseState = { ...urlState, starred: stars && urlState.starred }
  const key = keyOf(state)
  const urlRef = useRef(urlState)
  urlRef.current = urlState

  // The page in hand: the server's until a fetch replaces it. A new server
  // render (a navigation, a refresh) re-seeds it, adjust-during-render.
  const [held, setHeld] = useState(served)
  const [prevServed, setPrevServed] = useState(served)
  if (served !== prevServed) {
    setPrevServed(served)
    setHeld(served)
  }
  const stale = keyOf(held.state) !== key
  const [failed, setFailed] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  // A star toggle changes the starred count and, under the Starred chip, the
  // rows; the refetch is silent (no dim) once the toggle has settled.
  const [starsTick, setStarsTick] = useState(0)
  const starsSeen = useRef(starSet)
  useEffect(() => {
    if (starsSeen.current === starSet) return
    starsSeen.current = starSet
    const id = setTimeout(() => setStarsTick((n) => n + 1), STARS_SETTLE_MS)
    return () => clearTimeout(id)
  }, [starSet])
  const fetched = useRef({ starsTick: 0, attempt: 0 })

  useEffect(() => {
    const wanted =
      stale || fetched.current.starsTick !== starsTick || fetched.current.attempt !== attempt
    if (!wanted) return
    const controller = new AbortController()
    const snapshot = { ...state }
    bffFetch<PapersList>(listPath(snapshot), { signal: controller.signal })
      .then((list) => {
        fetched.current = { starsTick, attempt }
        setHeld({ state: snapshot, list })
        setFailed(null)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        console.error('[papers] page fetch failed:', error)
        setFailed(key)
      })
    return () => controller.abort()
    // `state` is derived from `key`; `starsTick`/`attempt` are the other two reasons to fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, starsTick, attempt, stale])

  const domainsRef = useRef(domains)
  domainsRef.current = domains
  const update = useCallback((patch: Partial<BrowseState>) => {
    // From the address bar as it is now, not the forced state and not the
    // last render's: only the rendered value is forced (a chip click must not
    // quietly drop a `?starred=1` the reader never cleared), and two writes
    // inside one render — a reset, then the search settling — must build on
    // each other.
    const current = stateFrom(
      Object.fromEntries(new URLSearchParams(window.location.search)),
      domainsRef.current,
    )
    const next = { ...current, ...patch }
    // A narrower or wider list starts again from its first page.
    if (!('page' in patch)) next.page = 1
    // No navigation: the App Router picks the query up from history and
    // `useSearchParams` re-renders; the server reads it again on a real visit.
    window.history.replaceState(null, '', window.location.pathname + searchOf(next))
  }, [])

  // The search text is the reader's, settling into the URL after a pause; the
  // URL's `q` re-seeds it on Back or a Home hand-over.
  const [text, setText] = useState(urlState.q)
  const [prevQ, setPrevQ] = useState(urlState.q)
  if (urlState.q !== prevQ) {
    setPrevQ(urlState.q)
    setText(urlState.q)
  }
  useEffect(() => {
    const q = text.trim()
    if (q === urlRef.current.q) return
    const id = setTimeout(() => update({ q }), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [text, update])
  const setSearch = (value: string) => {
    setText(value)
    if (value === '') update({ q: '' })
  }

  const { list } = held
  const { facets } = list
  const count = list.count
  const pageCount = Math.max(1, Math.ceil(count / PER_PAGE))
  const current = Math.min(state.page, pageCount)
  // A page past the end (filters narrowed under a stale `?page=`) folds back.
  useEffect(() => {
    if (!stale && count > 0 && list.results.length === 0 && state.page > 1) {
      update({ page: pageCount })
    }
  }, [stale, count, list.results.length, state.page, pageCount, update])

  const domainNames = new Map(domains.map((w) => [w.id, w.name]))
  const manyDomains = domains.length > 1
  const dimensionSorts = facets.dimension_sorts
  const sortLabel = (s: Sort) =>
    s === 'signal'
      ? state.q
        ? t('Relevance')
        : t('Signal score')
      : s === 'recent'
        ? t('Most recent')
        : (dimensionSorts.find((d) => `dim:${d.key}` === s)?.name ?? t('Signal score'))

  const trlNarrowed = facets.has_trl && (state.minTrl > 1 || state.maxTrl < 9)
  const filtersActive =
    state.domain !== null ||
    state.starred ||
    state.screening !== 'passed' ||
    trlNarrowed ||
    state.q !== '' ||
    state.withinDays > 0 ||
    state.minScore > 0
  // Narrowed filters read as removable chips above; this line carries only what
  // the chips don't say — the defaults still in force, and the query.
  const filterContext = [
    state.screening === 'passed' && t('through screening'),
    state.withinDays === 0 && t('full corpus'),
    state.q !== '' && fmt(t('matching “{q}”'), { q: state.q }),
  ]
    .filter(Boolean)
    .join(' · ')

  function resetFilters() {
    setText('')
    update({ ...DEFAULT_STATE, sort: urlRef.current.sort })
  }

  const chips = [
    state.domain !== null && {
      key: 'domain',
      label: domainNames.get(state.domain) ?? '',
      clear: () => update({ domain: null }),
    },
    state.screening !== 'passed' && {
      key: 'screening',
      label: t(screeningOptions.find((o) => o.id === state.screening)?.label ?? ''),
      clear: () => update({ screening: 'passed' }),
    },
    state.withinDays > 0 && {
      key: 'ingested',
      label: t(ingestedWindows.find((w) => w.days === state.withinDays)?.label ?? ''),
      clear: () => update({ withinDays: 0 }),
    },
    state.minScore > 0 && {
      key: 'signal',
      label: fmt(t('Signal ≥ {n}'), { n: state.minScore }),
      clear: () => update({ minScore: 0 }),
    },
    trlNarrowed && {
      key: 'trl',
      label: `TRL ${state.minTrl}–${state.maxTrl}`,
      clear: () => update({ minTrl: 1, maxTrl: 9 }),
    },
  ].filter(Boolean) as { key: string; label: string; clear: () => void }[]

  const pending = stale && failed !== key

  return (
    <div className="space-y-6">
      <SearchField value={text} onChange={setSearch} resultCount={count} />

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {chips.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={c.clear}
              className="group flex items-center gap-1.5 rounded-full border border-zinc-950/10 bg-white py-1 pr-1.5 pl-2.5 text-xs text-zinc-600 hover:border-zinc-400 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-500"
            >
              {c.label}
              <XMarkIcon className="size-3.5 text-zinc-400 group-hover:text-zinc-950 dark:group-hover:text-white" />
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Results sit beside the navigation; filters move to the right edge. */}
        <div className="lg:col-span-2">
          <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-zinc-500 dark:text-zinc-400">
            <p>
              <span className="font-mono font-medium text-zinc-950 tabular-nums dark:text-white">
                {count}
              </span>{' '}
              {count === 1 ? t('paper') : t('papers')}
              {filterContext && (
                <span className="text-zinc-400 dark:text-zinc-500"> · {filterContext}</span>
              )}
            </p>
            {facets.hidden_by_screening > 0 && count > 0 && (
              <ScreeningHint
                n={facets.hidden_by_screening}
                onShow={() => update({ screening: 'all' })}
              />
            )}
            {stars && (
              <StarredChip
                active={state.starred}
                count={facets.starred_count}
                onToggle={() => update({ starred: !urlRef.current.starred })}
              />
            )}
            {filtersActive && (
              <button
                type="button"
                onClick={resetFilters}
                className="ml-auto font-medium text-zinc-600 hover:text-zinc-950 dark:text-zinc-300 dark:hover:text-white"
              >
                {t('Reset filters')}
              </button>
            )}
          </div>
          {facets.truncated && (
            <p className="mb-3 text-xs text-zinc-400 dark:text-zinc-500">
              {fmt(t('Showing the newest {n} of {m} papers'), {
                n: facets.truncated.shown,
                m: facets.truncated.total,
              })}
            </p>
          )}
          {failed === key && (
            <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
              {t('Could not load these papers.')}{' '}
              <button
                type="button"
                onClick={() => setAttempt((n) => n + 1)}
                className="font-medium text-zinc-700 underline-offset-2 hover:underline dark:text-zinc-200"
              >
                {t('Retry')}
              </button>
            </p>
          )}
          <div
            className="space-y-3 transition-opacity duration-150 data-pending:opacity-60"
            data-pending={pending || undefined}
            aria-busy={pending || undefined}
          >
            {list.results.map((p) => (
              <PaperCard
                key={p.id}
                paper={p}
                domain={manyDomains ? domainNames.get(p.workspace_id) : undefined}
              />
            ))}
            {count === 0 && (
              <div className="rounded-sm border border-dashed border-line p-10 text-center text-sm text-zinc-400">
                {state.starred && facets.starred_count === 0 ? (
                  t('Nothing starred yet.')
                ) : facets.hidden_by_screening > 0 ? (
                  <ScreeningHint
                    n={facets.hidden_by_screening}
                    onShow={() => update({ screening: 'all' })}
                  />
                ) : (
                  t('No papers match these filters.')
                )}
              </div>
            )}
          </div>
          <PageNav
            page={current}
            pageCount={pageCount}
            onChange={(page) => update({ page })}
            className="mt-6"
            labels={{ prev: t('Previous'), next: t('Next') }}
          />
        </div>

        {/* Filters */}
        <aside className="divide-y divide-line max-lg:order-first lg:col-span-1">
          {manyDomains && (
            <FilterGroup
              label={t('Domain')}
              value={
                state.domain === null ? t('All domains') : (domainNames.get(state.domain) ?? '')
              }
            >
              <div className="space-y-1">
                <OptionButton
                  active={state.domain === null}
                  onClick={() => update({ domain: null })}
                  label={t('All domains')}
                />
                {domains.map((w) => (
                  <OptionButton
                    key={w.id}
                    active={state.domain === w.id}
                    onClick={() => update({ domain: w.id })}
                    label={w.name}
                  />
                ))}
              </div>
            </FilterGroup>
          )}

          <FilterGroup label={t('Sort by')} value={sortLabel(state.sort)}>
            <div className="space-y-1">
              {[
                { id: 'signal', label: t('Signal score') },
                { id: 'recent', label: t('Most recent') },
                ...dimensionSorts.map((d) => ({ id: `dim:${d.key}`, label: d.name })),
              ].map((s) => (
                <OptionButton
                  key={s.id}
                  active={state.sort === s.id}
                  onClick={() => update({ sort: s.id })}
                  label={s.label}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup
            label={t('Screening')}
            value={t(screeningOptions.find((o) => o.id === state.screening)?.label ?? '')}
          >
            <div className="space-y-1">
              {screeningOptions.map((o) => (
                <OptionButton
                  key={o.id}
                  active={state.screening === o.id}
                  onClick={() => update({ screening: o.id })}
                  label={t(o.label)}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup
            label={t('Ingested')}
            value={t(ingestedWindows.find((w) => w.days === state.withinDays)?.label ?? '')}
          >
            <div className="space-y-1">
              {ingestedWindows.map((w) => (
                <OptionButton
                  key={w.days}
                  active={state.withinDays === w.days}
                  onClick={() => update({ withinDays: w.days })}
                  label={t(w.label)}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup
            label={t('Signal strength')}
            value={state.minScore > 0 ? `≥ ${state.minScore}` : t('Any')}
          >
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{t('Minimum score')}</span>
              <span className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                {state.minScore > 0 ? state.minScore : t('Any')}
              </span>
            </div>
            <input
              type="range"
              aria-label={t('Minimum score')}
              min={0}
              max={facets.score_ceiling}
              step={5}
              value={state.minScore}
              onChange={(e) => update({ minScore: Number(e.target.value) })}
              className="rs-slider"
              style={
                {
                  '--fill': `${(state.minScore / facets.score_ceiling) * 100}%`,
                } as React.CSSProperties
              }
            />
            <div className="mt-1.5 flex justify-between text-xs text-zinc-400">
              <span>{t('Any signal')}</span>
              <span>{t('Only the strongest')}</span>
            </div>
          </FilterGroup>

          {facets.has_trl && (
            <FilterGroup
              label={t('TRL window')}
              value={trlNarrowed ? `TRL ${state.minTrl}–${state.maxTrl}` : t('Any')}
            >
              <div className="mb-1.5 flex items-center justify-between">
                <SectionLabel>{t('TRL window')}</SectionLabel>
                <span className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                  {state.minTrl}–{state.maxTrl}
                </span>
              </div>
              <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
                <TrlSelect
                  name="min-trl"
                  ariaLabel={t('Minimum TRL')}
                  value={state.minTrl}
                  onChange={(v) => update({ minTrl: Math.min(v, urlRef.current.maxTrl) })}
                />
                <span className="text-zinc-400">{t('to')}</span>
                <TrlSelect
                  name="max-trl"
                  ariaLabel={t('Maximum TRL')}
                  value={state.maxTrl}
                  onChange={(v) => update({ maxTrl: Math.max(v, urlRef.current.minTrl) })}
                />
              </div>
              <div className="mt-2 space-y-0.5 text-xs text-zinc-400">
                <div>{t('1–3 research')}</div>
                <div>{t('4–6 development')}</div>
                <div>{t('7–9 deployment')}</div>
              </div>
            </FilterGroup>
          )}
        </aside>
      </div>
    </div>
  )
}

function OptionButton({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm',
        active
          ? 'bg-zinc-950/5 text-zinc-950 dark:bg-white/10 dark:text-white'
          : 'text-zinc-600 hover:bg-zinc-950/5 dark:text-zinc-300 dark:hover:bg-white/5',
      )}
    >
      <span
        aria-hidden="true"
        className={clsx('size-1.5 shrink-0', active ? 'bg-accent' : 'bg-transparent')}
      />
      {label}
    </button>
  )
}

/**
 * A search that only the screening filter is hiding hits from: say so, and
 * offer the one click that shows them. Nobody should read "no papers match"
 * when the match is sitting behind a default.
 */
function ScreeningHint({ n, onShow }: { n: number; onShow: () => void }) {
  const t = useT()
  return (
    <button
      type="button"
      onClick={onShow}
      className="text-left font-medium text-blue-700 hover:underline dark:text-blue-300"
    >
      {fmt(t('{n} more matches in other screening states — show them'), { n })}
    </button>
  )
}

/** The primary way into the corpus: one wide field, always in reach. */
function SearchField({
  value,
  onChange,
  resultCount,
}: {
  value: string
  onChange: (value: string) => void
  resultCount: number
}) {
  const t = useT()
  const ref = useRef<HTMLInputElement>(null)

  return (
    <SearchFrame>
      <input
        ref={ref}
        name="search"
        type="search"
        aria-label={t('Search papers')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            onChange('')
            ref.current?.blur()
          }
        }}
        placeholder={t('Search titles, abstracts, authors, arXiv ids…')}
        className="min-w-0 flex-1 bg-transparent text-base text-zinc-950 placeholder:text-zinc-400 focus:outline-none dark:text-white [&::-webkit-search-cancel-button]:hidden"
      />
      {value !== '' && (
        <>
          <span className="shrink-0 font-mono text-xs text-zinc-400 tabular-nums">
            {fmt(t('{n} hits'), { n: resultCount })}
          </span>
          <button
            type="button"
            onClick={() => {
              onChange('')
              ref.current?.focus()
            }}
            aria-label={t('Clear search')}
            className="shrink-0 rounded-md p-1 text-zinc-400 hover:bg-zinc-950/5 hover:text-zinc-950 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <XMarkIcon className="size-4" />
          </button>
        </>
      )}
    </SearchFrame>
  )
}

/**
 * A collapsible filter group: label on the left, the group's current selection
 * on the right, and a chevron toggle. Open by default. The right-hand value
 * lets the whole filter state read at a glance — even with a group collapsed.
 */
function FilterGroup({
  label,
  value,
  children,
}: {
  label: string
  value?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="py-5 first:pt-0 last:pb-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="group flex w-full items-center justify-between gap-3"
      >
        <SectionLabel className="shrink-0">{label}</SectionLabel>
        <span className="flex min-w-0 items-center gap-2">
          {value && (
            <span className="truncate text-xs text-zinc-500 dark:text-zinc-400">{value}</span>
          )}
          <ChevronDownIcon
            className={clsx(
              'size-4 shrink-0 text-zinc-400 transition-transform group-hover:text-zinc-600 dark:group-hover:text-zinc-300',
              !open && '-rotate-90',
            )}
          />
        </span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

function TrlSelect({
  name,
  ariaLabel,
  value,
  onChange,
}: {
  name: string
  ariaLabel: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <span className="inline-grid grid-cols-[1fr_--spacing(8)]">
      <select
        name={name}
        aria-label={ariaLabel}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="col-span-full row-start-1 appearance-none rounded-md border border-zinc-950/10 bg-white py-1 pr-8 pl-2 dark:border-white/10 dark:bg-zinc-900"
      >
        {Array.from({ length: 9 }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      <svg
        viewBox="0 0 8 5"
        width="8"
        height="5"
        fill="none"
        className="pointer-events-none col-start-2 row-start-1 place-self-center"
      >
        <path d="M.5.5 4 4 7.5.5" stroke="currentcolor" />
      </svg>
    </span>
  )
}

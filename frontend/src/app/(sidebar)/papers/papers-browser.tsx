'use client'

import { PageNav } from '@/components/page-nav'
import { PaperCard } from '@/components/paper-card'
import { SectionLabel } from '@/components/scanner-ui'
import { StarredChip } from '@/components/star'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { isPassed } from '@/lib/papers/map'
import {
  byValueDesc,
  dimensionByKey,
  numericDefinitions,
  trlDimension,
  unionDefinitions,
} from '@/lib/papers/select'
import type { ScoredPaper, ScreeningStatus, WorkspaceSummary } from '@/lib/papers/types'
import { useStars } from '@/lib/stars-client'
import { ChevronDownIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useMemo, useRef, useState } from 'react'

const PER_PAGE = 8

/** 'signal' | 'recent' | 'dim:<definition key>' */
type Sort = string

type Screening = 'passed' | 'borderline' | 'pending' | 'rejected' | 'withdrawn' | 'all'

const screeningOptions: { id: Screening; label: string }[] = [
  { id: 'passed', label: 'Passed' },
  { id: 'borderline', label: 'Borderline' },
  { id: 'pending', label: 'Pending' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'withdrawn', label: 'Withdrawn' },
  { id: 'all', label: 'All statuses' },
]

function matchesScreening(status: ScreeningStatus, filter: Screening): boolean {
  if (filter === 'all') return true
  if (filter === 'passed') return isPassed(status)
  return status === filter
}

// Recent-time windows count back from the newest paper's ingest time (not
// wall-clock now), so "Last 24 hours" resolves to the freshest drop even in
// a corpus that hasn't been refreshed today.
const ingestedWindows = [
  { days: 1, label: 'Last 24 hours' },
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'This quarter' },
  { days: 0, label: 'All time' },
]

export function PapersBrowser({
  papers,
  workspaces,
}: {
  papers: ScoredPaper[]
  /** The domains the corpus spans — their definitions drive the sort options. */
  workspaces: WorkspaceSummary[]
}) {
  const t = useT()
  const { isStarred } = useStars()
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('all')
  const [starredOnly, setStarredOnly] = useState(false)
  const [screening, setScreening] = useState<Screening>('passed')
  const [sort, setSort] = useState<Sort>('signal')
  const [minTrl, setMinTrl] = useState(1)
  const [maxTrl, setMaxTrl] = useState(9)
  const [withinDays, setWithinDays] = useState(0) // 0 = all time
  const [minScore, setMinScore] = useState(0) // 0 = no cutoff
  const [page, setPage] = useState(1)

  // Sort options come from the domains' definitions, not a fixed list: the
  // same key once, however many domains define it.
  const dimensionSorts = useMemo(
    () =>
      numericDefinitions({ definitions: unionDefinitions(workspaces) }, papers).filter(
        (d) => !d.is_trl,
      ),
    [workspaces, papers],
  )
  const domainNames = useMemo(() => new Map(workspaces.map((w) => [w.id, w.name])), [workspaces])
  const manyDomains = workspaces.length > 1
  const hasTrl = useMemo(
    () => papers.some((p) => trlDimension(p)?.value !== null && trlDimension(p) !== undefined),
    [papers],
  )
  const sortLabel = (s: Sort) =>
    s === 'signal'
      ? t('Signal score')
      : s === 'recent'
        ? t('Most recent')
        : (dimensionSorts.find((d) => `dim:${d.key}` === s)?.name ?? t('Signal score'))

  // The score slider spans 0–100 unless the workspace formula scores higher.
  const scoreCeiling = useMemo(
    () => Math.max(100, Math.ceil(papers.reduce((m, p) => Math.max(m, p.signal_score ?? 0), 0))),
    [papers],
  )

  const newest = useMemo(
    () => papers.reduce((m, p) => (p.created_at > m ? p.created_at : m), ''),
    [papers],
  )

  const filtered = useMemo(() => {
    // Anchor the ingest window to the newest paper (pure); with no papers
    // there is nothing to window anyway.
    const cutoff = newest ? new Date(newest) : null
    cutoff?.setDate(cutoff.getDate() - withinDays)
    const q = search.toLowerCase()
    const result = papers.filter((p) => {
      if (domain !== 'all' && p.workspace_id !== domain) return false
      if (starredOnly && !isStarred('paper', p.id)) return false
      if (!matchesScreening(p.screening_status, screening)) return false
      if (hasTrl && (minTrl > 1 || maxTrl < 9)) {
        const trl = trlDimension(p)?.value ?? null
        if (trl === null || trl < minTrl || trl > maxTrl) return false
      }
      if (withinDays > 0 && cutoff && new Date(p.created_at) < cutoff) return false
      if (minScore > 0 && (p.signal_score === null || p.signal_score < minScore)) return false
      if (
        q &&
        !(
          p.title.toLowerCase().includes(q) ||
          p.abstract.toLowerCase().includes(q) ||
          p.authors_raw.toLowerCase().includes(q) ||
          (p.arxiv_id ?? '').toLowerCase().includes(q) ||
          (p.doi ?? '').toLowerCase().includes(q)
        )
      )
        return false
      return true
    })
    result.sort((a, b) => {
      if (sort === 'recent') return b.created_at.localeCompare(a.created_at)
      if (sort.startsWith('dim:')) {
        const key = sort.slice(4)
        return byValueDesc(
          dimensionByKey(a, key)?.value ?? null,
          dimensionByKey(b, key)?.value ?? null,
        )
      }
      return byValueDesc(a.signal_score, b.signal_score)
    })
    return result
  }, [
    papers,
    domain,
    search,
    screening,
    sort,
    minTrl,
    maxTrl,
    withinDays,
    minScore,
    newest,
    hasTrl,
    starredOnly,
    isStarred,
  ])
  // The Starred chip's count spans the corpus, whatever else is narrowed.
  const starredCount = useMemo(
    () => papers.filter((p) => isStarred('paper', p.id)).length,
    [papers, isStarred],
  )

  // Paginate the filtered corpus, eight at a time. Any filter or sort change
  // resets to the first page so the view never lands past the last result.
  const pageCount = Math.max(1, Math.ceil(filtered.length / PER_PAGE))
  const filterKey = [
    domain,
    starredOnly,
    search,
    screening,
    sort,
    minTrl,
    maxTrl,
    withinDays,
    minScore,
  ].join('\u0000')
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey)
  if (prevFilterKey !== filterKey) {
    // Adjust-during-render (not an effect): filters moved, back to page one.
    setPrevFilterKey(filterKey)
    setPage(1)
  }
  const current = Math.min(page, pageCount)
  const paged = filtered.slice((current - 1) * PER_PAGE, current * PER_PAGE)

  const trlNarrowed = hasTrl && (minTrl > 1 || maxTrl < 9)
  const filtersActive =
    domain !== 'all' ||
    starredOnly ||
    screening !== 'passed' ||
    trlNarrowed ||
    search !== '' ||
    withinDays > 0 ||
    minScore > 0
  // Narrowed filters read as removable chips above; this line carries only what
  // the chips don't say — the defaults still in force, and the query.
  const filterContext = [
    screening === 'passed' && t('through screening'),
    withinDays === 0 && t('full corpus'),
    search !== '' && fmt(t('matching “{q}”'), { q: search }),
  ]
    .filter(Boolean)
    .join(' · ')

  function resetFilters() {
    setDomain('all')
    setStarredOnly(false)
    setSearch('')
    setScreening('passed')
    setMinTrl(1)
    setMaxTrl(9)
    setWithinDays(0)
    setMinScore(0)
  }

  const chips = [
    domain !== 'all' && {
      key: 'domain',
      label: domainNames.get(domain) ?? '',
      clear: () => setDomain('all'),
    },
    screening !== 'passed' && {
      key: 'screening',
      label: t(screeningOptions.find((o) => o.id === screening)?.label ?? ''),
      clear: () => setScreening('passed'),
    },
    withinDays > 0 && {
      key: 'ingested',
      label: t(ingestedWindows.find((w) => w.days === withinDays)?.label ?? ''),
      clear: () => setWithinDays(0),
    },
    minScore > 0 && {
      key: 'signal',
      label: fmt(t('Signal ≥ {n}'), { n: minScore }),
      clear: () => setMinScore(0),
    },
    trlNarrowed && {
      key: 'trl',
      label: `TRL ${minTrl}–${maxTrl}`,
      clear: () => {
        setMinTrl(1)
        setMaxTrl(9)
      },
    },
  ].filter(Boolean) as { key: string; label: string; clear: () => void }[]

  return (
    <div className="space-y-6">
      <SearchField value={search} onChange={setSearch} resultCount={filtered.length} />

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
                {filtered.length}
              </span>{' '}
              {filtered.length === 1 ? t('paper') : t('papers')}
              {filterContext && (
                <span className="text-zinc-400 dark:text-zinc-500"> · {filterContext}</span>
              )}
            </p>
            <StarredChip
              active={starredOnly}
              count={starredCount}
              onToggle={() => setStarredOnly((v) => !v)}
            />
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
          <div className="space-y-3">
            {paged.map((p) => (
              <PaperCard
                key={p.id}
                paper={p}
                domain={manyDomains ? domainNames.get(p.workspace_id) : undefined}
              />
            ))}
            {filtered.length === 0 && (
              <div className="border-line rounded-sm border border-dashed p-10 text-center text-sm text-zinc-400">
                {starredOnly && starredCount === 0
                  ? t('Nothing starred yet.')
                  : t('No papers match these filters.')}
              </div>
            )}
          </div>
          <PageNav
            page={current}
            pageCount={pageCount}
            onChange={setPage}
            className="mt-6"
            labels={{ prev: t('Previous'), next: t('Next') }}
          />
        </div>

        {/* Filters */}
        <aside className="divide-line divide-y max-lg:order-first lg:col-span-1">
          {manyDomains && (
            <FilterGroup
              label={t('Domain')}
              value={domain === 'all' ? t('All domains') : (domainNames.get(domain) ?? '')}
            >
              <div className="space-y-1">
                <OptionButton
                  active={domain === 'all'}
                  onClick={() => setDomain('all')}
                  label={t('All domains')}
                />
                {workspaces.map((w) => (
                  <OptionButton
                    key={w.id}
                    active={domain === w.id}
                    onClick={() => setDomain(w.id)}
                    label={w.name}
                  />
                ))}
              </div>
            </FilterGroup>
          )}

          <FilterGroup label={t('Sort by')} value={sortLabel(sort)}>
            <div className="space-y-1">
              {[
                { id: 'signal', label: t('Signal score') },
                { id: 'recent', label: t('Most recent') },
                ...dimensionSorts.map((d) => ({ id: `dim:${d.key}`, label: d.name })),
              ].map((s) => (
                <OptionButton
                  key={s.id}
                  active={sort === s.id}
                  onClick={() => setSort(s.id)}
                  label={s.label}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup
            label={t('Screening')}
            value={t(screeningOptions.find((o) => o.id === screening)?.label ?? '')}
          >
            <div className="space-y-1">
              {screeningOptions.map((o) => (
                <OptionButton
                  key={o.id}
                  active={screening === o.id}
                  onClick={() => setScreening(o.id)}
                  label={t(o.label)}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup
            label={t('Ingested')}
            value={t(ingestedWindows.find((w) => w.days === withinDays)?.label ?? '')}
          >
            <div className="space-y-1">
              {ingestedWindows.map((w) => (
                <OptionButton
                  key={w.days}
                  active={withinDays === w.days}
                  onClick={() => setWithinDays(w.days)}
                  label={t(w.label)}
                />
              ))}
            </div>
          </FilterGroup>

          <FilterGroup
            label={t('Signal strength')}
            value={minScore > 0 ? `≥ ${minScore}` : t('Any')}
          >
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{t('Minimum score')}</span>
              <span className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                {minScore > 0 ? minScore : t('Any')}
              </span>
            </div>
            <input
              type="range"
              aria-label={t('Minimum score')}
              min={0}
              max={scoreCeiling}
              step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="rs-slider"
              style={{ '--fill': `${(minScore / scoreCeiling) * 100}%` } as React.CSSProperties}
            />
            <div className="mt-1.5 flex justify-between text-xs text-zinc-400">
              <span>{t('Any signal')}</span>
              <span>{t('Only the strongest')}</span>
            </div>
          </FilterGroup>

          {hasTrl && (
            <FilterGroup
              label={t('TRL window')}
              value={trlNarrowed ? `TRL ${minTrl}–${maxTrl}` : t('Any')}
            >
              <div className="mb-1.5 flex items-center justify-between">
                <SectionLabel>{t('TRL window')}</SectionLabel>
                <span className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                  {minTrl}–{maxTrl}
                </span>
              </div>
              <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
                <TrlSelect
                  name="min-trl"
                  ariaLabel={t('Minimum TRL')}
                  value={minTrl}
                  onChange={setMinTrl}
                />
                <span className="text-zinc-400">{t('to')}</span>
                <TrlSelect
                  name="max-trl"
                  ariaLabel={t('Maximum TRL')}
                  value={maxTrl}
                  onChange={setMaxTrl}
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
    <div className="group focus-within:border-accent/60 focus-within:ring-accent/15 border-line bg-surface relative flex items-center gap-3 rounded-md border px-4 py-3 transition focus-within:ring-4">
      <MagnifyingGlassIcon className="group-focus-within:text-accent size-5 shrink-0 text-zinc-400 transition-colors" />
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
    </div>
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

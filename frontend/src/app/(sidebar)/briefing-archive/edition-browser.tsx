'use client'

import { AnswerMarkdown, AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { DomainBadge, SignalScore } from '@/components/scanner-ui'
import { SearchFrame } from '@/components/search-frame'
import { Bone } from '@/components/skeleton'
import { StarButton, StarredChip, StarToggle } from '@/components/star'
import { ALL_ON, type Features } from '@/lib/features'
import { useFeatures } from '@/lib/features-client'
import { fmt, type Lang } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { paperHref } from '@/lib/papers/href'
import { useStars } from '@/lib/stars-client'
import { XMarkIcon } from '@heroicons/react/20/solid'
import clsx from 'clsx'
import Link from 'next/link'
import { useMemo, useRef, useState, type ReactNode, type Ref } from 'react'
import { editionHref, formatEditionDate } from '../briefing/format'

export interface BrowserEdition {
  /** The run that produced it — the identity, since two domains can share a date. */
  runId: string
  workspaceId: string
  /** The domain's display name. */
  domain: string
  date: string
  title: string
  inBrief: string
  /** 'template' until the backend's reporting step writes model prose. */
  proseSource: 'model' | 'template'
  funnel: { screened: number; included: number; inBriefing: number }
  papers: { id: string; title: string; signal: number | null }[]
}

/* ---------------------------------- Frames --------------------------------- */

/**
 * The archive as a reading room: search spans the top, the selected brief
 * reads on the left two-thirds, and the edition history is the sticky right
 * rail. EditionBrowser and EditionBrowserSkeleton both fill it.
 */
function EditionBrowserFrame({
  state,
  search,
  reader,
  readerRef,
  railLabel,
  rail,
}: {
  state: 'loaded' | 'skeleton'
  search: ReactNode
  reader: ReactNode
  readerRef?: Ref<HTMLDivElement>
  railLabel: string
  rail: ReactNode
}) {
  return (
    <div data-shape="edition-browser" data-state={state} className="space-y-6">
      {search}

      {/* Same grid as Papers/Ask: the reader spans 2/3, history is the right 1/3. */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* min-w-0: the reader's one-line date row must truncate, not widen the column. */}
        <div ref={readerRef} className="min-w-0 scroll-mt-24 lg:col-span-2">
          {reader}
        </div>

        {/* History: above the reader on mobile, the right 1/3 on desktop. */}
        <nav
          aria-label={railLabel}
          className="min-w-0 max-lg:order-first lg:sticky lg:top-24 lg:col-span-1 lg:self-start"
        >
          {rail}
        </nav>
      </div>
    </div>
  )
}

function ReaderFrame({
  date,
  link,
  title,
  star,
  funnel,
  brief,
  count,
  papers,
}: {
  date: ReactNode
  link: ReactNode
  title: ReactNode
  /** The briefing's star toggle, left of the link (a 30px control in both states). */
  star: ReactNode
  funnel: ReactNode
  brief: ReactNode
  count: ReactNode
  papers: ReactNode
}) {
  return (
    <article
      data-row="reader"
      className="rounded-2xl border border-line-soft bg-white p-6 shadow-xs sm:p-8 dark:bg-zinc-900/40"
    >
      {/* On desktop one line that never wraps: the date group truncates, the
          star and the link keep their width — so the loaded reader and its
          skeleton stay the same height whatever the domain is called. On a
          phone the controls drop under the date instead of eating it. */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 lg:flex-nowrap">
        <div className="flex min-w-0 items-baseline gap-2 overflow-hidden font-mono text-[11px] tracking-[0.14em] whitespace-nowrap text-zinc-400 uppercase dark:text-zinc-500">
          {date}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {star}
          {link}
        </div>
      </div>
      <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-zinc-950 dark:text-white">
        {title}
      </h2>
      <p className="mt-2 font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
        {funnel}
      </p>

      {brief}

      <div className="mt-6 border-t border-line-soft pt-5">
        <div className="font-mono text-[11px] font-medium tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
          {count}
        </div>
        <ol className="mt-3 space-y-3">{papers}</ol>
      </div>
    </article>
  )
}

const READER_LINK = 'text-xs font-medium text-blue-600 hover:underline dark:text-blue-400'
const BRIEF_CLASS = 'mt-5 max-w-2xl text-sm text-pretty text-zinc-600 dark:text-zinc-300'
const PAPER_LINK =
  'min-w-0 flex-1 truncate text-sm font-medium text-zinc-800 hover:underline dark:text-zinc-100'

function PaperRow({ score, title }: { score: ReactNode; title: ReactNode }) {
  return (
    <li data-row="paper" className="flex items-center gap-3">
      {score}
      {title}
    </li>
  )
}

const RAIL_COUNT =
  'px-1 font-mono text-[11px] tracking-wide text-zinc-400 tabular-nums dark:text-zinc-500'
const RAIL_LIST = '-mx-1 mt-2 max-h-[70vh] space-y-0.5 overflow-y-auto pr-1 lg:pb-4'
// pr-9 keeps the date line clear of the row's corner star.
const RAIL_ROW = 'relative block w-full rounded-lg py-3 pr-9 pl-4 text-left transition-colors'
/** The count line and, on the loaded rail, the Starred chip beside it. */
const RAIL_HEAD = 'flex items-center justify-between gap-3 pr-1'

function RailRowBody({
  current = false,
  date,
  title,
}: {
  current?: boolean
  date: ReactNode
  title: ReactNode
}) {
  return (
    <>
      <span
        aria-hidden="true"
        className={clsx(
          'absolute top-3 bottom-3 left-0 w-0.5 rounded-full transition-colors',
          current
            ? 'bg-accent'
            : 'bg-transparent group-hover:bg-zinc-300 dark:group-hover:bg-zinc-600',
        )}
      />
      {/* One line, whatever the domain is called: the date keeps its width,
          the domain truncates, so a long name never grows the row. */}
      <div
        className={clsx(
          'flex min-w-0 items-baseline gap-2 font-mono text-[11px] tracking-wide whitespace-nowrap tabular-nums',
          current ? 'text-zinc-700 dark:text-zinc-200' : 'text-zinc-400 dark:text-zinc-500',
        )}
      >
        {date}
      </div>
      <p
        className={clsx(
          'mt-1 text-sm leading-snug',
          current
            ? 'font-medium text-zinc-950 dark:text-white'
            : 'text-zinc-600 group-hover:text-zinc-900 dark:text-zinc-300 dark:group-hover:text-white',
        )}
      >
        {title}
      </p>
    </>
  )
}

/* ---------------------------------- Loaded --------------------------------- */

export function EditionBrowser({ editions, lang }: { editions: BrowserEdition[]; lang: Lang }) {
  const t = useT()
  const { isStarred } = useStars()
  const { stars } = useFeatures()
  const searchRef = useRef<HTMLInputElement>(null)
  const readerRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [starredOnlyState, setStarredOnly] = useState(false)
  const [activeId, setActiveId] = useState(editions[0]?.runId)

  // The effective filter, not the state. The rail has no Reset, so a flip
  // taken with the chip engaged would otherwise leave `filtered` starred-only,
  // `active` null and both panes saying "Nothing starred yet." with no control
  // left to clear it — a dead end short of a hard reload.
  const starredOnly = stars && starredOnlyState

  const starredCount = useMemo(
    () => editions.filter((e) => isStarred('briefing', e.runId)).length,
    [editions, isStarred],
  )
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return editions.filter(
      (e) =>
        (!starredOnly || isStarred('briefing', e.runId)) &&
        (!q ||
          [e.title, e.inBrief, ...e.papers.map((p) => p.title)]
            .join(' ')
            .toLowerCase()
            .includes(q)),
    )
  }, [editions, query, starredOnly, isStarred])

  // Keep the reader on a still-visible edition when a search narrows the
  // list; the Starred filter is stricter — the reader honours it too.
  const active =
    filtered.find((e) => e.runId === activeId) ??
    (starredOnly ? null : editions.find((e) => e.runId === activeId)) ??
    filtered[0] ??
    null
  const emptyCopy =
    starredOnly && starredCount === 0
      ? t('Nothing starred yet.')
      : t('No briefings match your search.')

  function select(runId: string) {
    setActiveId(runId)
    // Only nudge the reader into view on the stacked (mobile) layout.
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      readerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <EditionBrowserFrame
      state="loaded"
      readerRef={readerRef}
      railLabel={t('Briefing history')}
      search={
        <SearchFrame>
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
        </SearchFrame>
      }
      reader={
        active ? (
          <ReaderFrame
            date={
              <>
                {/* When the line is tight, the domain name gives way (it truncates); the date and the chip hold. */}
                <span className="shrink-0">{formatEditionDate(active.date, lang)}</span>
                <DomainBadge name={active.domain} tone="quiet" className="min-w-0 normal-case" />
                {active.proseSource === 'template' && (
                  <span className="shrink-0 rounded-sm border border-line px-1 py-px normal-case">
                    {t('auto-brief')}
                  </span>
                )}
              </>
            }
            link={
              <Link
                href={editionHref(active.date, active.workspaceId, { runId: active.runId })}
                className={READER_LINK}
              >
                {t('Open briefing →')}
              </Link>
            }
            title={active.title}
            // The attribute stays — ReaderFrame's `star` is required, and
            // omitting it is a typecheck error — only the value goes.
            star={
              stars ? <StarToggle kind="briefing" id={active.runId} className="shrink-0" /> : null
            }
            funnel={fmt(
              t('{screened} screened → {included} included → {inBriefing} in the briefing'),
              {
                screened: active.funnel.screened,
                included: active.funnel.included,
                inBriefing: active.funnel.inBriefing,
              },
            )}
            brief={<AnswerMarkdown text={active.inBrief} className={BRIEF_CLASS} />}
            count={
              active.papers.length === 1
                ? t('1 paper')
                : fmt(t('{n} papers'), { n: active.papers.length })
            }
            papers={active.papers.map((p) => (
              <PaperRow
                key={p.id}
                score={<SignalScore score={p.signal} size="sm" />}
                title={
                  <Link href={paperHref(p.id, { runId: active.runId })} className={PAPER_LINK}>
                    {p.title}
                  </Link>
                }
              />
            ))}
          />
        ) : (
          <div className="rounded-sm border border-dashed border-line p-10 text-center text-sm text-zinc-400">
            {emptyCopy}
          </div>
        )
      }
      rail={
        <>
          <div className={RAIL_HEAD}>
            <p className={RAIL_COUNT}>
              {fmt(t('{n} of {total} briefings'), { n: filtered.length, total: editions.length })}
            </p>
            {stars && (
              <StarredChip
                active={starredOnly}
                count={starredCount}
                onToggle={() => setStarredOnly((v) => !v)}
              />
            )}
          </div>
          <ul className={RAIL_LIST}>
            {filtered.map((e) => {
              const current = active?.runId === e.runId
              const isToday = e.runId === editions[0]?.runId
              return (
                // `group` on the item: the row button and the corner star
                // are siblings (a button cannot hold a button).
                <li key={e.runId} data-row="edition" className="group relative">
                  <button
                    type="button"
                    onClick={() => select(e.runId)}
                    aria-current={current ? 'true' : undefined}
                    className={clsx(
                      RAIL_ROW,
                      current
                        ? 'bg-zinc-950/[0.04] dark:bg-white/[0.06]'
                        : 'group-hover:bg-zinc-950/[0.025] dark:group-hover:bg-white/[0.03]',
                    )}
                  >
                    <RailRowBody
                      current={current}
                      date={
                        <>
                          <span className="shrink-0">{formatEditionDate(e.date, lang)}</span>
                          <span className="min-w-0 truncate">· {e.domain}</span>
                          {isToday && <span className="shrink-0 text-accent">{t('Today')}</span>}
                        </>
                      }
                      title={<span className="line-clamp-2 block">{e.title}</span>}
                    />
                  </button>
                  {/* The `group relative` <li> stays either way: it also drives
                      the row's hover background. */}
                  {stars && (
                    <StarButton kind="briefing" id={e.runId} className="absolute top-2 right-1.5" />
                  )}
                </li>
              )
            })}
            {filtered.length === 0 && (
              <li className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-zinc-400 dark:text-zinc-500">
                {emptyCopy}
              </li>
            )}
          </ul>
        </>
      }
    />
  )
}

/* --------------------------------- Skeleton -------------------------------- */

const PAPER_WIDTHS = [['58%'], ['44%'], ['66%']]

/**
 * The reading room's bones. `editions` is the rail's row count, `papers` the
 * reader's list; `briefParagraphs` and `railLines` mirror the loaded prose
 * so the gallery can pass the fixture's shape.
 */
export function EditionBrowserSkeleton({
  editions = 6,
  papers = 5,
  briefParagraphs = [3, 2],
  railLines = [2],
  features = ALL_ON,
}: {
  editions?: number
  papers?: number
  briefParagraphs?: number[]
  railLines?: number[]
  /** Optional: the Studio gallery renders this skeleton directly, all-on. */
  features?: Features
}) {
  const t = useT()
  return (
    <EditionBrowserFrame
      state="skeleton"
      railLabel={t('Briefing history')}
      search={
        <SearchFrame>
          <span className="min-w-0 flex-1 text-base">
            <Bone.Text widths={['30ch']} />
          </span>
        </SearchFrame>
      }
      reader={
        <ReaderFrame
          date={<Bone.Text widths={['20ch']} />}
          link={
            <span className="text-xs font-medium">
              <Bone.Text widths={['12ch']} />
            </span>
          }
          title={<Bone.Text widths={['70%']} />}
          star={features.stars ? <Bone.Block className="h-[30px] w-28 shrink-0" /> : null}
          funnel={<Bone.Text widths={['34ch']} />}
          brief={<AnswerMarkdownSkeleton className={BRIEF_CLASS} paragraphs={briefParagraphs} />}
          count={<Bone.Text widths={['8ch']} />}
          papers={Array.from({ length: papers }, (_, i) => (
            <PaperRow
              key={i}
              score={<Bone.Ring size={40} stroke={4} />}
              title={
                <span className="min-w-0 flex-1 text-sm font-medium">
                  <Bone.Text widths={PAPER_WIDTHS[i % PAPER_WIDTHS.length]} />
                </span>
              }
            />
          ))}
        />
      }
      rail={
        <>
          <div className={RAIL_HEAD}>
            <p className={RAIL_COUNT}>
              <Bone.Text widths={['14ch']} />
            </p>
            {features.stars && <Bone.Chip width={82} />}
          </div>
          <ul className={RAIL_LIST}>
            {Array.from({ length: editions }, (_, i) => (
              <li key={i} data-row="edition">
                <div className={RAIL_ROW}>
                  <RailRowBody
                    date={<Bone.Text widths={['20ch']} />}
                    title={
                      <Bone.Text lines={railLines[i % railLines.length]} widths={['100%', '70%']} />
                    }
                  />
                </div>
              </li>
            ))}
          </ul>
        </>
      }
    />
  )
}

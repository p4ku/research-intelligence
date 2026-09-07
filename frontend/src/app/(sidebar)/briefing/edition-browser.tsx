'use client'

import { AnswerMarkdown, AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { DomainBadge, SignalScore } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { fmt, type Lang } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/20/solid'
import clsx from 'clsx'
import Link from 'next/link'
import { useMemo, useRef, useState, type ReactNode, type Ref } from 'react'
import { editionHref, formatEditionDate } from './format'

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
        <div ref={readerRef} className="scroll-mt-24 lg:col-span-2">
          {reader}
        </div>

        {/* History: above the reader on mobile, the right 1/3 on desktop. */}
        <nav
          aria-label={railLabel}
          className="max-lg:order-first lg:sticky lg:top-24 lg:col-span-1 lg:self-start"
        >
          {rail}
        </nav>
      </div>
    </div>
  )
}

/** The search box that spans the full width above both panes, as on Papers. */
function SearchFrame({ children }: { children: ReactNode }) {
  return (
    <div className="group relative flex items-center gap-3 rounded-md border border-line bg-surface px-4 py-3 transition focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent/15">
      <MagnifyingGlassIcon className="size-5 shrink-0 text-zinc-400 transition-colors group-focus-within:text-accent" />
      {children}
    </div>
  )
}

function ReaderFrame({
  date,
  link,
  title,
  funnel,
  brief,
  count,
  papers,
}: {
  date: ReactNode
  link: ReactNode
  title: ReactNode
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
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex items-baseline gap-2 font-mono text-[11px] tracking-[0.14em] text-zinc-400 uppercase dark:text-zinc-500">
          {date}
        </div>
        {link}
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
const RAIL_ROW = 'group relative block w-full rounded-lg py-3 pr-3 pl-4 text-left transition-colors'

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
  const searchRef = useRef<HTMLInputElement>(null)
  const readerRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [activeId, setActiveId] = useState(editions[0]?.runId)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return editions
    return editions.filter((e) =>
      [e.title, e.inBrief, ...e.papers.map((p) => p.title)].join(' ').toLowerCase().includes(q),
    )
  }, [editions, query])

  // Keep the reader on a still-visible edition when a search narrows the list.
  const active =
    filtered.find((e) => e.runId === activeId) ??
    editions.find((e) => e.runId === activeId) ??
    filtered[0] ??
    null

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
                {formatEditionDate(active.date, lang)}
                <DomainBadge name={active.domain} tone="quiet" className="normal-case" />
                {active.proseSource === 'template' && (
                  <span className="rounded-sm border border-line px-1 py-px normal-case">
                    {t('auto-brief')}
                  </span>
                )}
              </>
            }
            link={
              <Link href={editionHref(active.date, active.workspaceId)} className={READER_LINK}>
                {t('Open briefing →')}
              </Link>
            }
            title={active.title}
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
                  <Link href={`/papers/${p.id}`} className={PAPER_LINK}>
                    {p.title}
                  </Link>
                }
              />
            ))}
          />
        ) : (
          <div className="rounded-sm border border-dashed border-line p-10 text-center text-sm text-zinc-400">
            {t('No briefings match your search.')}
          </div>
        )
      }
      rail={
        <>
          <p className={RAIL_COUNT}>
            {fmt(t('{n} of {total} briefings'), { n: filtered.length, total: editions.length })}
          </p>
          <ul className={RAIL_LIST}>
            {filtered.map((e) => {
              const current = active?.runId === e.runId
              const isToday = e.runId === editions[0]?.runId
              return (
                <li key={e.runId} data-row="edition">
                  <button
                    type="button"
                    onClick={() => select(e.runId)}
                    aria-current={current ? 'true' : undefined}
                    className={clsx(
                      RAIL_ROW,
                      current
                        ? 'bg-zinc-950/[0.04] dark:bg-white/[0.06]'
                        : 'hover:bg-zinc-950/[0.025] dark:hover:bg-white/[0.03]',
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
                </li>
              )
            })}
            {filtered.length === 0 && (
              <li className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-zinc-400 dark:text-zinc-500">
                {t('No briefings match your search.')}
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
}: {
  editions?: number
  papers?: number
  briefParagraphs?: number[]
  railLines?: number[]
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
          <p className={RAIL_COUNT}>
            <Bone.Text widths={['14ch']} />
          </p>
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

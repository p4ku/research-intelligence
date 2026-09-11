import { Bone } from '@/components/skeleton'
import { StarToggle } from '@/components/star'
import { ALL_ON, type Features } from '@/lib/features'
import { fmt, formatDate, type Lang, type T } from '@/lib/i18n'
import { paperExportHref } from '@/lib/papers/href'
import type { ScoredPaper } from '@/lib/papers/types'
import { ArrowDownTrayIcon, ArrowUpRightIcon, BookmarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { AbstractDisclosure } from './abstract'
import { RiskAffiliationFlagging } from './affiliation-flags'

/**
 * The record's masthead: provenance on one line (the source, the
 * publication date when the backend has it and the ingest date otherwise,
 * the link out to the original paper), the title, the authors, the metadata
 * card (risk & affiliation rows and chips with the collapsed abstract as
 * its last row), and at the right the export link and the star.
 * PaperHeaderFrame owns the layout so PaperHeader and PaperHeaderSkeleton
 * cannot drift.
 */

const META = 'text-xs text-zinc-400'

function Dot() {
  return <span className={META}>·</span>
}

export function PaperHeaderFrame({
  state = 'loaded',
  meta,
  title,
  authors,
  children,
  action,
}: {
  state?: 'loaded' | 'skeleton'
  meta: ReactNode
  title: ReactNode
  authors: ReactNode
  children?: ReactNode
  /** The export link and the star toggle, right of the masthead. */
  action?: ReactNode
}) {
  return (
    <div
      data-shape="paper-header"
      data-state={state}
      className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between"
    >
      <div className="min-w-0 flex-1">
        <div data-row="meta" className="flex flex-wrap items-center gap-2">
          {meta}
        </div>
        <h1
          data-row="title"
          className="mt-2 text-2xl font-semibold tracking-tight text-pretty break-words text-zinc-950 sm:text-[28px] sm:leading-[1.2] dark:text-white"
        >
          {title}
        </h1>
        <p data-row="authors" className="mt-2.5 text-[15px] text-zinc-500 dark:text-zinc-400">
          {authors}
        </p>
        {children}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  )
}

/**
 * The paper's printable record, opened in its own tab
 * (app/(document)/papers/[id]/export) where it prints itself: the browser's
 * dialog then saves it as a PDF. A plain link, not a button: it navigates,
 * needs no script, and the tab is where the reader lands. Cut to the star's
 * own chip so the two read as one row of quiet actions.
 */
export function ExportPdfLink({ id, runId, t }: { id: string; runId?: string; t: T }) {
  return (
    <a
      href={paperExportHref(id, { runId })}
      target="_blank"
      rel="noopener"
      data-row="export-pdf"
      className={clsx(
        'inline-flex h-[30px] shrink-0 items-center gap-1.5 rounded-sm border border-line bg-surface px-2.5 text-xs font-medium whitespace-nowrap text-zinc-600 transition-colors duration-150 ease-out',
        'hover:border-zinc-400 hover:text-zinc-950 active:scale-[0.98]',
        'dark:text-zinc-300 dark:hover:border-zinc-500 dark:hover:text-white',
      )}
    >
      <ArrowDownTrayIcon aria-hidden="true" className="size-3.5 text-zinc-400" />
      {t('Export PDF')}
    </a>
  )
}

export function PaperHeader({
  paper,
  runId,
  t,
  lang,
  features = ALL_ON,
}: {
  paper: ScoredPaper
  /** The briefing the paper was opened from; the export keeps that reading. */
  runId?: string
  t: T
  lang: Lang
  features?: Features
}) {
  return (
    <PaperHeaderFrame
      meta={
        <>
          {paper.is_benchmark && (
            <>
              <span
                data-row="benchmark-control"
                className="inline-flex items-center gap-1 rounded-sm bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700 ring-1 ring-violet-700/20 dark:bg-violet-950/40 dark:text-violet-300 dark:ring-violet-400/30"
              >
                <BookmarkIcon aria-hidden="true" className="size-3" />
                <span>
                  {paper.evaluation_label
                    ? `${t('Benchmark Control')} (${paper.evaluation_label === 'passed' ? t('Passed') : t('Rejected')})`
                    : t('Benchmark Control')}
                </span>
              </span>
              <Dot />
            </>
          )}
          <span className={META}>{paper.source}</span>
          <Dot />
          <span className={META}>
            {paper.published_date
              ? fmt(t('Published {date}'), { date: formatDate(paper.published_date, lang) })
              : formatDate(paper.created_at, lang)}
          </span>
          {paper.source_url && (
            <>
              <Dot />
              <a
                href={paper.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-0.5 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
              >
                {t('View original paper')}
                <ArrowUpRightIcon aria-hidden="true" className="size-3" />
              </a>
            </>
          )}
        </>
      }
      title={paper.title}
      authors={
        Array.isArray(paper.authors)
          ? paper.authors.join(', ') || paper.authors_raw
          : paper.authors || paper.authors_raw || ''
      }
      action={
        <>
          <ExportPdfLink id={paper.id} runId={runId} t={t} />
          {features.stars && <StarToggle kind="paper" id={paper.id} />}
        </>
      }
    >
      <RiskAffiliationFlagging
        risk={paper.risk_and_affiliation}
        abstract={paper.abstract ? <AbstractDisclosure text={paper.abstract} /> : undefined}
        t={t}
      />
    </PaperHeaderFrame>
  )
}

export function PaperHeaderSkeleton({ features = ALL_ON }: { features?: Features }) {
  return (
    <PaperHeaderFrame
      state="skeleton"
      meta={
        <>
          <Bone.Text widths={['5ch']} className={META} />
          <Dot />
          <Bone.Text widths={['11ch']} className={META} />
          <Dot />
          <Bone.Text widths={['16ch']} className={META} />
        </>
      }
      title={<Bone.Text lines={2} widths={['92%', '55%']} />}
      authors={<Bone.Text widths={['60%']} />}
      action={
        <>
          <Bone.Block className="h-[30px] w-[100px]" />
          {features.stars && <Bone.Block className="h-[30px] w-24" />}
        </>
      }
    >
      {/* The metadata card in its usual shape: an affiliation line, a
          funding line, a chip row and the collapsed abstract row — what
          almost every scored paper has (the fixture and the stakeholder's
          prod examples alike). The bones sit in the abstract slot, so the
          card is one shape here and on load. A paper with no risk data
          loses the upper rows on load; one with no abstract loses the card. */}
      <RiskAffiliationFlagging
        abstract={
          <>
            <div data-row="affiliation" className="flex h-4 items-center">
              <Bone.Text widths={['30ch']} className="text-xs" />
            </div>
            <div data-row="funding" className="flex h-4 items-center">
              <Bone.Text widths={['44ch']} className="text-[11px]" />
            </div>
            <div data-row="flags" className="flex flex-wrap gap-2 pt-0.5">
              <Bone.Block className="h-[22px] w-36 rounded-md" />
              <Bone.Block className="h-[22px] w-44 rounded-md" />
              <Bone.Block className="h-[22px] w-40 rounded-md" />
            </div>
            <div data-row="abstract-disclosure" className="flex min-h-6 items-center">
              <Bone.Text widths={['9ch']} className="text-[11px]" />
            </div>
          </>
        }
      />
    </PaperHeaderFrame>
  )
}

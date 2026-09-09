import { Bone } from '@/components/skeleton'
import { StarToggle } from '@/components/star'
import { ALL_ON, type Features } from '@/lib/features'
import { formatDate, type Lang, type T } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import { ArrowUpRightIcon, BookmarkIcon } from '@heroicons/react/16/solid'
import type { ReactNode } from 'react'
import { RiskAffiliationFlagging } from './affiliation-flags'

/**
 * The record's masthead: provenance on one line (the source, the
 * publication date when the backend has it and the ingest date otherwise,
 * the link out to the original paper), the title, the authors, the risk &
 * affiliation flagging card, and the star at the right.
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
  /** The star toggle, right of the masthead. */
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
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function PaperHeader({
  paper,
  t,
  lang,
  features = ALL_ON,
}: {
  paper: ScoredPaper
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
              ? `${t('Published')} ${formatDate(paper.published_date, lang)}`
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
      // Withheld, not rendered null: PaperHeaderFrame's `{action && …}` would
      // otherwise wrap an empty node in a shrink-0 flex item and open a gap
      // beside the masthead on a narrow viewport.
      action={features.stars ? <StarToggle kind="paper" id={paper.id} /> : undefined}
    >
      <RiskAffiliationFlagging risk={paper.risk_and_affiliation} />
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
      action={features.stars ? <Bone.Block className="h-[30px] w-24" /> : undefined}
    />
  )
}

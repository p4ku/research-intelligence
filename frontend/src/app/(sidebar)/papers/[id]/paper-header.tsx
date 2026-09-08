import { ScreeningPill } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { StarToggle } from '@/components/star'
import { ALL_ON, type Features } from '@/lib/features'
import { formatDate, type Lang, type T } from '@/lib/i18n'
import { arxivId } from '@/lib/papers/map'
import type { ScoredPaper } from '@/lib/papers/types'
import { ArrowUpRightIcon } from '@heroicons/react/16/solid'
import type { ReactNode } from 'react'

/**
 * The record's masthead: screening pill and provenance on one line (the
 * source, the publication date when the backend has it and the ingest date
 * otherwise, the link out to the original paper), the title, the authors,
 * and the star at the right. PaperHeaderFrame owns the layout so PaperHeader and
 * PaperHeaderSkeleton cannot drift.
 *
 * Both take the demo flags, defaulting to ALL_ON because the skeleton gallery
 * renders them directly with no such prop. Nothing in the masthead answers to
 * `all_papers`; the prop is here so the star affordance in the `action` slot
 * has the flags to read.
 *
 * `stars` is now wired, and it is wired as a withhold rather than a null
 * render: both signatures read `features.stars` and pass `undefined` into the
 * `action` slot when it is off, so PaperHeaderFrame drops the wrapping
 * `shrink-0` div entirely instead of keeping an empty flex item that opens a
 * gap beside the masthead on a narrow viewport. Same rule in the skeleton, or
 * the bone promises a control the loaded row never grows.
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
  action,
}: {
  state?: 'loaded' | 'skeleton'
  meta: ReactNode
  title: ReactNode
  authors: ReactNode
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
          className="mt-2 max-w-[30ch] text-[28px] leading-[1.15] font-semibold tracking-tight text-balance text-zinc-950 dark:text-white"
        >
          {title}
        </h1>
        <p data-row="authors" className="mt-2.5 text-[15px] text-zinc-500 dark:text-zinc-400">
          {authors}
        </p>
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
  const arxiv = arxivId(paper.arxiv_id)
  return (
    <PaperHeaderFrame
      meta={
        <>
          <ScreeningPill status={paper.screening_status} t={t} />
          <Dot />
          <span className={META}>{paper.source}</span>
          <Dot />
          <span className={META}>
            {paper.published_date
              ? `${t('Published')} ${formatDate(paper.published_date, lang)}`
              : formatDate(paper.created_at, lang)}
          </span>
          {arxiv && (
            <>
              <Dot />
              <span className="font-mono text-xs text-zinc-400">arXiv:{arxiv}</span>
            </>
          )}
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
      authors={paper.authors.join(', ') || paper.authors_raw}
      // Withheld, not rendered null: PaperHeaderFrame's `{action && …}` would
      // otherwise wrap an empty node in a shrink-0 flex item and open a gap
      // beside the masthead on a narrow viewport.
      action={features.stars ? <StarToggle kind="paper" id={paper.id} /> : undefined}
    />
  )
}

export function PaperHeaderSkeleton({ features = ALL_ON }: { features?: Features }) {
  return (
    <PaperHeaderFrame
      state="skeleton"
      meta={
        <>
          <Bone.Chip width={104} />
          <Dot />
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

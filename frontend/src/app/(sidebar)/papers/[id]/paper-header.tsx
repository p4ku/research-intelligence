import { ScreeningPill, SectionLabel } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { formatDate, type Lang, type T } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import type { ReactNode } from 'react'

/**
 * The record's masthead: screening pill and provenance on one line, the
 * title, the authors. PaperHeaderFrame owns the layout so PaperHeader and
 * PaperHeaderSkeleton cannot drift.
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
}: {
  state?: 'loaded' | 'skeleton'
  meta: ReactNode
  title: ReactNode
  authors: ReactNode
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
          className="mt-2 text-2xl leading-tight font-semibold tracking-tight text-zinc-950 dark:text-white"
        >
          {title}
        </h1>
        <p data-row="authors" className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          {authors}
        </p>
      </div>
    </div>
  )
}

export function PaperHeader({ paper, t, lang }: { paper: ScoredPaper; t: T; lang: Lang }) {
  return (
    <PaperHeaderFrame
      meta={
        <>
          <ScreeningPill status={paper.screening_status} t={t} />
          <Dot />
          <span className={META}>{paper.source}</span>
          <Dot />
          <span className={META}>{formatDate(paper.created_at, lang)}</span>
          {paper.arxiv_id && (
            <>
              <Dot />
              <span className="font-mono text-xs text-zinc-400">arXiv:{paper.arxiv_id}</span>
            </>
          )}
        </>
      }
      title={paper.title}
      authors={paper.authors.join(', ') || paper.authors_raw}
    />
  )
}

export function PaperHeaderSkeleton() {
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
        </>
      }
      title={<Bone.Text widths={['85%']} />}
      authors={<Bone.Text widths={['60%']} />}
    />
  )
}

/** The signal card's heading in its ledger branch; the skeleton reserves that branch. */
export function SignalHeading({ t }: { t: T }) {
  return (
    <>
      <SectionLabel>{t('Signal score')}</SectionLabel>
      <p className="mt-1 text-xs text-zinc-400">
        {t('What the score is made of — and what would move it.')}
      </p>
    </>
  )
}

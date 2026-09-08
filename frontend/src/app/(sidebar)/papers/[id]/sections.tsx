import { AnswerMarkdown } from '@/components/answer-markdown'
import { SectionLabel } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import type { Features } from '@/lib/features'
import { formatDate, type Lang, type T } from '@/lib/i18n'
import { arxivIdOf, doiOf } from '@/lib/papers/map'
import { byValueDesc } from '@/lib/papers/select'
import { PASSED_STATUSES, type ScoredPaper } from '@/lib/papers/types'
import { ArrowUpRightIcon } from '@heroicons/react/16/solid'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { AssessmentRows } from './assessment-rows'
import { PaperChat } from './paper-chat'
import { PaperHeader } from './paper-header'
import { PaperNav, type PaperNeighbours } from './paper-nav'
import { ScoreRail } from './score-rail'

/**
 * The paper page's streamed sections. Everything comes from one `papers.get`
 * (React-cached, so the crumb, the metadata and the record share the call),
 * which is why the record is a single boundary rather than one per card.
 *
 * The layout is the "sidecar": the record reads top to bottom in one column
 * (masthead, screening, assessment, abstract, provenance) with the score
 * card sticky beside it, and the paper's chat behind a pill that opens a
 * sheet — so the scores stay in view while the reasoning is read.
 */

/** The title crumb — the only thing above the record that needs the fetch. */
export async function PaperCrumb({ id }: { id: string }) {
  const result = await forPage(papers.get(id))
  return result ? result.paper.title : null
}

/**
 * Previous / next within the domain, in signal order — the lists' default
 * sort. A failed list is no neighbours, never a failed page.
 */
async function neighboursOf(paper: ScoredPaper): Promise<PaperNeighbours | null> {
  const corpus = await papers.listAll(paper.workspace_id).catch(() => null)
  if (!corpus) return null
  const ordered = corpus.papers
    .filter((p) => PASSED_STATUSES.includes(p.screening_status))
    .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
  const i = ordered.findIndex((p) => p.id === paper.id)
  if (i < 0) return null
  return {
    prev: i > 0 ? `/papers/${ordered[i - 1]!.id}` : null,
    next: i < ordered.length - 1 ? `/papers/${ordered[i + 1]!.id}` : null,
    position: i + 1,
    total: ordered.length,
  }
}

export async function PaperRecord({
  id,
  t,
  lang,
  features,
}: {
  id: string
  t: T
  lang: Lang
  features: Features
}) {
  const result = await forPage(papers.get(id))
  // The shell has already streamed, so this renders (sidebar)/not-found.tsx
  // in place with HTTP 200 — the trade for an instant shell, recorded in
  // docs/skeletons.md.
  if (!result) notFound()
  const { paper } = result
  // With the list hidden the pager is not rendered, so the corpus fetch that
  // feeds it is not made either: skipping the request is the point.
  const neighbours = features.all_papers ? await neighboursOf(paper) : null

  return (
    <div className="mt-6">
      <PaperNav neighbours={neighbours} t={t} features={features} />

      <div className="mt-6 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-9">
          <PaperHeader paper={paper} t={t} lang={lang} features={features} />

          <section>
            <SectionLabel>{t('Screening')}</SectionLabel>
            {paper.screening_reasoning ? (
              <AnswerMarkdown
                text={paper.screening_reasoning}
                className="mt-3 max-w-[76ch] text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300"
              />
            ) : (
              <p className="mt-3 text-sm text-zinc-400">{t('No screening notes.')}</p>
            )}
          </section>

          <section>
            <SectionLabel className="mb-3">{t('Assessment')}</SectionLabel>
            <AssessmentRows dimensions={paper.dimensions} />
          </section>

          <section>
            <SectionLabel>{t('Abstract')}</SectionLabel>
            <p className="mt-3 max-w-[76ch] text-[15px] leading-relaxed text-pretty text-zinc-700 dark:text-zinc-300">
              {paper.abstract}
            </p>
          </section>

          <Provenance paper={paper} t={t} lang={lang} />
        </div>

        <ScoreRail paper={paper} t={t} />
      </div>

      {/* Ask the paper: a scoped conversation in a sheet, opened from the pill. */}
      <PaperChat paper={paper} />
    </div>
  )
}

/** The link names itself: arXiv only for a shape-checked id, so a backfilled W-id link reads "Source". */
function sourceLabel(url: string, t: T): string {
  const arxiv = arxivIdOf(url)
  if (arxiv) return `arXiv ${arxiv}`
  const doi = doiOf(url)
  if (doi) return `DOI ${doi}`
  return t('Source')
}

/** Where the record came from, on one quiet line under the abstract. */
function Provenance({ paper, t, lang }: { paper: ScoredPaper; t: T; lang: Lang }) {
  const parts: React.ReactNode[] = []
  if (paper.source_url) {
    parts.push(
      <a
        key="src"
        href={paper.source_url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-0.5 font-medium text-blue-600 hover:underline dark:text-blue-400"
      >
        {sourceLabel(paper.source_url, t)}
        <ArrowUpRightIcon aria-hidden="true" className="size-3" />
      </a>,
    )
  }
  parts.push(
    <span key="added">
      {t('Ingested')} {formatDate(paper.created_at, lang)}
    </span>,
  )
  parts.push(
    <Link key="run" href={`/runs/${paper.pipeline_run_id}`} className="hover:underline">
      {t('Run')} <span className="font-mono">{paper.pipeline_run_id.slice(0, 8)}</span>
    </Link>,
  )
  return (
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line pt-4 text-xs text-zinc-400 dark:text-zinc-500">
      {parts.map((part, i) => (
        <span key={i} className="inline-flex items-center gap-3">
          {i > 0 && <span aria-hidden="true">·</span>}
          {part}
        </span>
      ))}
    </footer>
  )
}

import { Breadcrumbs, SectionLabel } from '@/components/scanner-ui'
import { editionHref } from '@/lib/bff/briefings/href'
import type { Edition } from '@/lib/bff/briefings/schema'
import { editionDate } from '@/lib/bff/briefings/select'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { runs } from '@/lib/bff/pipeline-runs/service'
import type { Features } from '@/lib/features'
import { fmt, formatDate, type Lang, type T } from '@/lib/i18n'
import { paperHref } from '@/lib/papers/href'
import { arxivIdOf, doiOf } from '@/lib/papers/map'
import { paperAsRun } from '@/lib/papers/runs'
import { byValueDesc } from '@/lib/papers/select'
import { PASSED_STATUSES, type ScoredPaper } from '@/lib/papers/types'
import { ArrowUpRightIcon } from '@heroicons/react/16/solid'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cache } from 'react'
import { formatEditionDate } from '../../briefing/format'
import { Assessment } from './assessment'
import { PaperChat } from './paper-chat'
import { PaperHeader } from './paper-header'
import { PaperNav, type PaperExit, type PaperNeighbours } from './paper-nav'
import { railParts } from './score-rail'

/**
 * The paper page's streamed sections. Everything comes from one `papers.get`
 * (React-cached, so the crumb, the metadata and the record share the call),
 * which is why the record is a single boundary rather than one per card.
 *
 * The layout is the "sidecar": the record reads top to bottom in one column
 * (masthead, abstract, then the assessment definition by
 * definition, provenance) with the score card sticky beside it — its bars
 * link into the assessment and mark the definition being read — and the
 * paper's chat composer directly under the card. A question typed there
 * opens the conversation in the rail itself: the card and the composer
 * become one console with the radar pinned at its top (paper-chat.tsx), so
 * the scores stay in view while the reasoning is read and the spider is
 * never covered.
 *
 * Opened from a briefing (`?run=`), the record is the paper as that run read
 * it: its decision, score and screening notes are the run's own row (the
 * same overlay the edition's cards apply — `paperAsRun`), the crumbs and the
 * back link lead to the edition, and prev / next walk the edition's papers.
 * Dimensions stay the paper's — extractions belong to the paper, not to a
 * run. A run the reader cannot see, or one that never recorded the paper,
 * resolves to no context at all, and the page is the paper as it stands.
 */

/**
 * The record's grid: reading column beside a 300px rail that widens to
 * 400px while the ask console is open (`:has`, so the client console needs
 * no hand on its parent). The record column dips once as it re-wraps —
 * blur masking a single reflow, per the motion rules. The skeleton shares
 * both, so the shell cannot drift from the page.
 */
export const RECORD_GRID =
  'group/record mt-6 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_300px] lg:has-[[data-console-open]]:grid-cols-[minmax(0,1fr)_400px]'
export const RECORD_COLUMN =
  'min-w-0 space-y-9 lg:group-has-[[data-console-open]]/record:animate-dip motion-reduce:animate-none'

/** The title crumb — the only thing above the record that needs the fetch. */
export async function PaperCrumb({ id }: { id: string }) {
  const result = await forPage(papers.get(id))
  return result ? result.paper.title : null
}

/** The briefing a `?run=` opens the paper in. */
export interface RunContext {
  run: PipelineRun
  /** The run's edition — null when the run briefed nothing. */
  edition: Edition | null
  /** The paper as the run recorded it (see lib/papers/runs `paperAsRun`). */
  paper: ScoredPaper
}

/**
 * The run named in the URL, when it recorded this paper: the run, its
 * edition and the paper as it read it. The run ledger is already in hand
 * for the request (the corpus snapshot reads it), so finding the run there
 * costs nothing; an id outside the reader's domains is simply not found.
 * The context is decoration on the record, so an upstream hiccup in any of
 * its reads degrades to "no run", never to an error page. Cached per
 * request: the crumbs and the record resolve it once between them.
 */
const runContext = cache(
  async (id: string, runId: string, lang: Lang): Promise<RunContext | null> => {
    try {
      const [result, ledger] = await Promise.all([papers.get(id, runId), runs.listEverywhere()])
      if (!result) return null
      const run = ledger.find((r) => r.id === runId) ?? null
      if (!run) return null
      const [found, index] = await Promise.all([
        briefings.getByDate(run.workspace_id, editionDate(run), lang, runId),
        papers.runIndex(),
      ])
      // getByDate falls back to the day's newest edition; only the run's own counts.
      const edition = found?.run_id === runId ? found : null
      const entry = edition?.papers.find((p) => p.id === id)
      const paper = paperAsRun(result.paper, runId, index, entry)
      return paper ? { run, edition, paper } : null
    } catch {
      return null
    }
  },
)

/** The edition's permalink and the words that lead to it. */
function exitTo(ctx: RunContext, t: T): PaperExit {
  return {
    href: editionHref(editionDate(ctx.run), ctx.run.workspace_id, { runId: ctx.run.id }),
    label: t('Back to briefing'),
  }
}

/**
 * The crumb trail for a paper opened from a briefing: Briefings, the
 * edition (domain and day, as the edition page names itself), the paper.
 * A run that does not resolve gets the plain trail, exactly as without
 * `?run=` — which, with the list hidden, is none.
 */
export async function RunCrumbs({
  id,
  runId,
  t,
  lang,
  features,
}: {
  id: string
  runId: string
  t: T
  lang: Lang
  features: Features
}) {
  const [ctx, result] = await Promise.all([
    runContext(id, runId, lang),
    forPage(papers.get(id, runId)),
  ])
  const title = result ? result.paper.title : null
  if (!ctx) {
    if (!features.all_papers) return null
    return <Breadcrumbs items={[{ label: t('Papers'), href: '/papers' }, { label: title }]} t={t} />
  }
  const day = editionDate(ctx.run)
  return (
    <Breadcrumbs
      items={[
        { label: t('Briefings'), href: '/briefing' },
        {
          label: `${ctx.run.workspace_name} · ${formatEditionDate(day, lang)}`,
          href: editionHref(day, ctx.run.workspace_id, { runId: ctx.run.id }),
        },
        { label: title },
      ]}
      t={t}
    />
  )
}

/**
 * Previous / next. Inside a briefing: the edition's papers in the order it
 * lists them, each link keeping the run. Otherwise — on its own, or from a
 * run that recorded the paper but briefed nothing — the domain's papers in
 * signal order, the lists' default sort. A failed list is no neighbours,
 * never a failed page.
 */
async function neighboursOf(
  paper: ScoredPaper,
  ctx: RunContext | null,
): Promise<PaperNeighbours | null> {
  if (ctx?.edition) {
    const ids = ctx.edition.papers.map((p) => p.id)
    const i = ids.indexOf(paper.id)
    if (i < 0) return null
    const to = (id: string) => paperHref(id, { runId: ctx.run.id })
    return {
      prev: i > 0 ? to(ids[i - 1]!) : null,
      next: i < ids.length - 1 ? to(ids[i + 1]!) : null,
      position: i + 1,
      total: ids.length,
    }
  }
  const corpus = await papers.listAll(paper.workspace_id).catch(() => null)
  if (!corpus) return null
  const ordered = corpus.papers
    .filter((p) => PASSED_STATUSES.includes(p.screening_status))
    .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
  const i = ordered.findIndex((p) => p.id === paper.id)
  if (i < 0) return null
  return {
    prev: i > 0 ? paperHref(ordered[i - 1]!.id) : null,
    next: i < ordered.length - 1 ? paperHref(ordered[i + 1]!.id) : null,
    position: i + 1,
    total: ordered.length,
  }
}

export async function PaperRecord({
  id,
  runId,
  sessionId = null,
  t,
  lang,
  features,
}: {
  id: string
  /** The briefing the paper was opened from, when the URL names one. */
  runId?: string
  /** The conversation the URL names (`?session=`); the console opens on it. */
  sessionId?: string | null
  t: T
  lang: Lang
  features: Features
}) {
  const [result, ctx] = await Promise.all([
    forPage(papers.get(id, runId)),
    runId ? runContext(id, runId, lang) : null,
  ])
  // The shell has already streamed, so this renders (sidebar)/not-found.tsx
  // in place with HTTP 200 — the trade for an instant shell, recorded in
  // docs/skeletons.md.
  if (!result) notFound()
  const paper = ctx ? ctx.paper : result.paper
  // With the list hidden the pager is not rendered, so the corpus fetch that
  // feeds it is not made either: skipping the request is the point. A
  // briefing's pager reads the edition, already fetched for the context.
  const neighbours = ctx?.edition || features.all_papers ? await neighboursOf(paper, ctx) : null

  return (
    <div className="mt-6">
      <PaperNav
        neighbours={neighbours}
        t={t}
        lang={lang}
        features={features}
        back={ctx ? exitTo(ctx, t) : undefined}
      />

      <div className={RECORD_GRID}>
        <div className={RECORD_COLUMN}>
          <PaperHeader paper={paper} t={t} lang={lang} features={features} />

          <section>
            <SectionLabel>{t('Abstract')}</SectionLabel>
            <p className="mt-3 max-w-[76ch] text-[15px] leading-relaxed text-pretty text-zinc-700 dark:text-zinc-300">
              {paper.abstract}
            </p>
          </section>

          <section>
            <SectionLabel className="mb-3">{t('Assessment')}</SectionLabel>
            <Assessment dimensions={paper.dimensions} t={t} lang={lang} />
          </section>

          <Provenance paper={paper} t={t} lang={lang} />
        </div>

        {/*
          The rail: the score card and, right under it, the ask composer.
          Open, the two become one console (paper-chat.tsx) and the rail
          column widens — the grid reads that off the console's attribute.
          Sticky as one unit so the scores stay in view while the assessment
          is read.
        */}
        <div className="lg:sticky lg:top-8">
          <PaperChat paper={paper} rail={railParts(paper, t, lang)} initialSessionId={sessionId} />
        </div>
      </div>
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

/** Where the record came from, on one quiet line under the assessment. */
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
      {fmt(t('Ingested {date}'), { date: formatDate(paper.created_at, lang) })}
    </span>,
  )
  parts.push(
    <Link key="run" href={`/runs/${paper.pipeline_run_id}`} className="hover:underline">
      {paper.pipeline_run_name ?? (
        <>
          {t('Run')} <span className="font-mono">{(paper.pipeline_run_id ?? '').slice(0, 8)}</span>
        </>
      )}
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

import { AnswerMarkdown } from '@/components/answer-markdown'
import { Breadcrumbs, SectionLabel, StatBand, type StatBandItem } from '@/components/scanner-ui'
import { StarToggle } from '@/components/star'
import type { Edition } from '@/lib/bff/briefings/schema'
import { byNewest } from '@/lib/bff/briefings/select'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import type { Features } from '@/lib/features'
import type { Lang, T } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cache } from 'react'
import { formatDay, formatTimestamp, periodLabel } from '../../dashboard/format'
import { editionHref, formatEditionDate } from '../format'
import { hasBriefing } from '../rows'
import { cardRows } from './card-rows'
import { EditionPaperList } from './edition-paper-list'

/**
 * One edition's streamed sections. The head needs the edition; the papers
 * need the edition and the scored corpus. Both services are React-cached, so
 * the two sections share one edition fetch. `wsId` and `runId` are the
 * domain and run from the URL; without them, the newest edition of the day
 * (in any domain, or in that domain) is shown.
 */

export function funnelCopy(t: T) {
  return [
    { label: t('Screened') },
    { label: t('Analysed') },
    { label: t('Period covered') },
    { label: t('Generated') },
  ]
}

/** Crumbs and title, the funnel, the brief. */
export async function EditionHead({
  wsId,
  runId,
  date,
  lang,
  t,
  domains,
  features,
  page = 1,
  minScore,
  sort,
}: {
  wsId?: string
  runId?: string
  date: string
  lang: Lang
  t: T
  /** Domain names by workspace id, for the crumb. */
  domains: Record<string, string>
  /** Required: page.tsx is the only caller, and its skeleton must agree. */
  features: Features
  page?: number
  minScore?: number
  sort?: string
}) {
  const edition = await forPage(
    briefings.findByDate(date, lang, wsId, runId, 'included', page, 20, minScore, sort),
  )
  // A date with no edition is a true 404 — rendered in-stream now that the
  // shell has already gone out (see docs/skeletons.md).
  if (!edition) notFound()

  // Resolve lightweight run record for period and timestamps via listAll (GET /api/pipeline-runs/, ~40ms, cached)
  // instead of the heavy detail endpoint (which computes S3 storage stats and transfers megabytes).
  const targetRunId = runId || edition.run_id
  const runList = await runsService.listAll(edition.workspace_id).catch(() => [])
  const run = runList.find((r) => r.id === targetRunId) ?? null
  const elsewhere = await namedElsewhere(runId, edition, lang)

  const copy = funnelCopy(t)
  const period = run ? periodLabel(run, t, lang) : formatDay(edition.date, lang)
  const instant = run?.completed_at ?? edition.generated_at ?? run?.started_at
  const generatedStamp = instant ? formatTimestamp(instant, lang) : formatDay(edition.date, lang)

  const funnel: StatBandItem[] = [
    { value: edition.funnel.fetched, ...copy[0] },
    { value: edition.funnel.passed_screening, ...copy[1] },
    { value: period, noFlow: true, ...copy[2] },
    { value: generatedStamp, noFlow: true, ...copy[3] },
  ]
  const domain = domains[edition.workspace_id]
  const dateLabel = formatEditionDate(edition.date, lang)

  return (
    <>
      <div className="space-y-4">
        {/* No title: the backend's `title` is the first paper's first word (10 Sep 2026).
            The crumb names the page; the star sits at its right, as a briefing is
            starred by its run. The heading stays for the outline, unseen. */}
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <Breadcrumbs
            items={[
              { label: t('Briefings'), href: '/briefing' },
              { label: domain ? `${domain} · ${dateLabel}` : dateLabel },
            ]}
            t={t}
          />
          <h1 className="sr-only">{domain ? `${domain} · ${dateLabel}` : dateLabel}</h1>
          {features.stars && <StarToggle kind="briefing" id={edition.run_id} />}
        </div>
        <StaleLinkNotice
          edition={edition}
          elsewhere={elsewhere}
          runId={runId}
          domains={domains}
          t={t}
          lang={lang}
        />
      </div>

      <StatBand items={funnel} flow />

      <section>
        <SectionLabel size="sm">{t('In brief')}</SectionLabel>
        <AnswerMarkdown
          text={edition.in_brief}
          className="mt-4 max-w-3xl text-base text-pretty text-zinc-600 dark:text-zinc-300"
        />
      </section>
    </>
  )
}

/**
 * The domain's briefings, newest first — those that are rows in the
 * ledgers (the same rule as `hasBriefing`), so the notice never offers an
 * edition the archive hides. The list is the one `findByDate` already read
 * under the composed source; a failed read is no list, never a failed
 * page. Cached per request; `namedElsewhere` is its only caller, and only
 * reaches it for a link whose run is not the briefing shown.
 */
const domainEditions = cache(async (edition: Edition, lang: Lang): Promise<Edition[]> => {
  const [all, capped] = await Promise.all([
    briefings.listAll(edition.workspace_id, lang).catch(() => []),
    briefings.capped().catch(() => false),
  ])
  return all.filter((e) => hasBriefing(e.funnel.passed_screening, e, capped)).sort(byNewest)
})

/**
 * The briefing a link's run names when it is not the one shown: a run of
 * another day in this domain, or of another domain altogether (a hand-edited
 * URL — the app mints `domain` and `run` together). The domain's own list
 * is asked first; only a run missing from it costs the every-domain read.
 * Null when the run is not a published briefing anywhere. Cached per
 * request, like `domainEditions`.
 *
 * The lists are read here, not by the caller: a link whose run is the one
 * shown — every link the app mints (#117) — needs neither, and reading the
 * domain's editions ahead of this check put a whole `/editions/?page_size=200`
 * on the critical path of a page that then renders no notice at all.
 */
export const namedElsewhere = cache(
  async (runId: string | undefined, edition: Edition, lang: Lang): Promise<Edition | null> => {
    if (!runId || runId === edition.run_id) return null
    const editions = await domainEditions(edition, lang)
    const inDomain = editions.find((e) => e.run_id === runId)
    if (inDomain) return inDomain
    const [all, capped] = await Promise.all([
      briefings.listEverywhere(lang).catch(() => []),
      briefings.capped().catch(() => false),
    ])
    return (
      all.find((e) => e.run_id === runId && hasBriefing(e.funnel.passed_screening, e, capped)) ??
      null
    )
  },
)

const NOTICE_LINK = 'font-medium text-blue-600 hover:underline dark:text-blue-400'

/**
 * One quiet line under the crumb when the URL's run is not the briefing
 * shown: a link naming a run of another day, or of another domain, points
 * at that briefing; a link naming a run that is no longer published (its
 * run passed nothing, or is gone) says so. Nothing otherwise — the day's
 * other briefings are not listed here (stakeholder edit, 10 Sep 2026); the
 * ledger is where a day's runs sit side by side. `sub` keeps the link on
 * the screening log when that is where the reader is.
 */
export function StaleLinkNotice({
  edition,
  elsewhere,
  runId,
  sub,
  domains,
  t,
  lang,
}: {
  edition: Edition
  /** The briefing the URL's run names when it is not this one (`namedElsewhere`). */
  elsewhere: Edition | null
  /** The run the URL named, if any. */
  runId?: string
  sub?: 'run'
  /** Domain names by workspace id, to name a briefing of another domain. */
  domains: Record<string, string>
  t: T
  lang: Lang
}) {
  if (!runId || runId === edition.run_id) return null
  // Another domain's briefing is named by its domain; this domain's by its day.
  const where = (e: Edition) => {
    const day = formatDay(e.date, lang)
    const name = e.workspace_id === edition.workspace_id ? null : domains[e.workspace_id]
    return name ? `${name} · ${day}` : day
  }
  return (
    <p className="text-sm text-zinc-500 dark:text-zinc-400">
      {elsewhere ? (
        <>
          {t('This link named a different briefing:')}{' '}
          <Link
            href={editionHref(elsewhere.date, elsewhere.workspace_id, {
              runId: elsewhere.run_id,
              sub,
            })}
            className={NOTICE_LINK}
          >
            {where(elsewhere)}
          </Link>
          .{' '}
        </>
      ) : (
        `${t('The briefing this link named is no longer published.')} `
      )}
      {t("Showing the day's briefing.")}
    </p>
  )
}

/** The papers that passed, as cards with their stars, and the link to the screening log. */
export async function EditionPapers({
  wsId,
  runId,
  date,
  lang,
  page = 1,
  minScore,
  sort,
}: {
  wsId?: string
  runId?: string
  date: string
  lang: Lang
  page?: number
  minScore?: number
  sort?: string
}) {
  const edition = await forPage(
    briefings.findByDate(date, lang, wsId, runId, 'included', page, 20, minScore, sort),
  )
  if (!edition) notFound()

  // If edition.papers already carries full scorecard records (from backend single-stream detail),
  // use them directly; otherwise resolve run rows via papersService as fallback.
  let cards: ScoredPaper[]
  const hasDimensions = edition.papers.some((p) => (p.dimensions?.length ?? 0) > 0)
  if (edition.papers.length === 0 || edition.papers[0]?.workspace_id || hasDimensions) {
    cards = edition.papers as unknown as ScoredPaper[]
  } else {
    const scored = await forPage(
      papersService.listRun(edition.workspace_id, edition.run_id, 'passed'),
    )
    const byId = new Map(scored.map((p) => [p.id, p]))
    cards = []
    for (const entry of edition.papers) {
      const paper = byId.get(entry.id)
      if (!paper) continue
      cards.push({
        ...paper,
        screening_status: entry.screening_status ?? paper.screening_status,
        signal_score: entry.signal_score,
      })
    }
  }

  const total = edition.total ?? edition.total_papers ?? edition.funnel.surfaced

  // Trimmed to what a card shows before crossing to the client: the rows as
  // read weigh ~21 KB each (card-rows.ts).
  return (
    <EditionPaperList
      papers={cardRows(cards)}
      runId={edition.run_id}
      logHref={editionHref(edition.date, edition.workspace_id, {
        runId: edition.run_id,
        sub: 'run',
      })}
      total={total}
      page={page}
      pageSize={20}
      definitions={edition.definitions}
    />
  )
}

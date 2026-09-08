import { AnswerMarkdown } from '@/components/answer-markdown'
import { Breadcrumbs, SectionLabel, StatBand } from '@/components/scanner-ui'
import { StarToggle } from '@/components/star'
import type { Edition } from '@/lib/bff/briefings/schema'
import { byNewest } from '@/lib/bff/briefings/select'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
import type { Features } from '@/lib/features'
import { fmt, type Lang, type T } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cache } from 'react'
import { clockStamp, formatDay } from '../../dashboard/format'
import { editionHref, formatEditionDate } from '../format'
import { hasBriefing } from '../rows'
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
    { label: t('Screened'), sub: t('matched the focus fields') },
    { label: t('Included'), sub: t('cleared the signal bar') },
    { label: t('In the briefing'), sub: t('listed below') },
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
}) {
  const edition = await forPage(briefings.findByDate(date, lang, wsId, runId))
  // A date with no edition is a true 404 — rendered in-stream now that the
  // shell has already gone out (see docs/skeletons.md).
  if (!edition) notFound()
  const siblings = await sameDayEditions(edition, lang)

  const copy = funnelCopy(t)
  const funnel = [
    { value: edition.funnel.fetched, ...copy[0] },
    { value: edition.funnel.passed_screening, ...copy[1] },
    { value: edition.funnel.surfaced, ...copy[2] },
  ]
  const domain = domains[edition.workspace_id]
  const dateLabel = formatEditionDate(edition.date, lang)

  return (
    <>
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: t('Briefings'), href: '/briefing' },
            { label: domain ? `${domain} · ${dateLabel}` : dateLabel },
          ]}
          t={t}
        />
        {/* The briefing's star sits at the title's right; a briefing is starred by its run. */}
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <h1 className="min-w-0 flex-1 text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
            {edition.title}
          </h1>
          {features.stars && <StarToggle kind="briefing" id={edition.run_id} className="mt-px" />}
        </div>
        <SameDayNotice edition={edition} siblings={siblings} runId={runId} t={t} lang={lang} />
      </div>

      <StatBand items={funnel} flow className="lg:grid-cols-3!" />

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
 * The domain's other briefings of the same day, newest first — those that
 * are rows in the ledgers (the same rule as `hasBriefing`), so the notice
 * never offers an edition the archive hides. The list is the one
 * `findByDate` already read under the composed source; a failed read is
 * no siblings, never a failed page. Cached per request: the edition page
 * and the screening log both ask.
 */
export const sameDayEditions = cache(async (edition: Edition, lang: Lang): Promise<Edition[]> => {
  const [all, capped] = await Promise.all([
    briefings.listAll(edition.workspace_id, lang).catch(() => []),
    papersService.corpusTruncated().catch(() => false),
  ])
  return all
    .filter(
      (e) =>
        e.date === edition.date &&
        e.run_id !== edition.run_id &&
        hasBriefing(e.funnel.passed_screening, e, capped),
    )
    .sort(byNewest)
})

/**
 * One quiet line under the title when the URL and the day do not tell the
 * whole story. A link that named this run (every link the app mints) lists
 * the day's other briefings; a link that did not — a bookmark from before
 * runs were in the URL — landed on the day's newest and says so, with the
 * earlier ones a click away; a link naming a run that is no longer
 * published (its run passed nothing, or is gone) says that first, even
 * when the day holds only this briefing. Nothing when the URL named this
 * run and the day holds no other.
 */
export function SameDayNotice({
  edition,
  siblings,
  runId,
  t,
  lang,
}: {
  edition: Edition
  /** The domain's other briefings of the day, newest first (`sameDayEditions`). */
  siblings: Edition[]
  /** The run the URL named, if any. */
  runId?: string
  t: T
  lang: Lang
}) {
  const named = runId === edition.run_id
  const substituted = Boolean(runId) && !named
  if (siblings.length === 0 && !substituted) return null
  const gone = substituted ? `${t('The briefing this link named is no longer published.')} ` : ''
  if (siblings.length === 0) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {gone}
        {t("Showing the day's briefing.")}
      </p>
    )
  }
  const lead = named
    ? t('Other briefings this day:')
    : `${gone}${fmt(t('This is the latest of {n} briefings for this domain on {day}.'), {
        n: siblings.length + 1,
        day: formatEditionDate(edition.date, lang),
      })} ${t('Earlier:')}`
  return (
    <p className="text-sm text-zinc-500 dark:text-zinc-400">
      {lead}{' '}
      {siblings.map((e, i) => (
        <span key={e.run_id}>
          {i > 0 && <span aria-hidden="true"> · </span>}
          <Link
            href={editionHref(e.date, e.workspace_id, { runId: e.run_id })}
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {e.generated_at ? clockStamp(e.generated_at) : formatDay(e.date, lang)}
          </Link>
        </span>
      ))}
    </p>
  )
}

/** The papers that passed, as cards with their stars, and the link to the screening log. */
export async function EditionPapers({
  wsId,
  runId,
  date,
  lang,
}: {
  wsId?: string
  runId?: string
  date: string
  lang: Lang
}) {
  const edition = await forPage(briefings.findByDate(date, lang, wsId, runId))
  if (!edition) notFound()
  // The run's own rows: the corpus's, or read live past the snapshot's cap.
  const scored = await forPage(papersService.listRun(edition.workspace_id, edition.run_id))

  // The card is the paper's scorecard as it stands today, but inside a frozen
  // edition its decision and score are the run's: a paper this run surfaced
  // at 76 must not read "Rejected · Unscored" because a later run said so.
  // Its dimensions stay current — extractions belong to the paper, not to a
  // run — so a re-extracted paper can show today's TRL beside the run's score.
  const byId = new Map(scored.map((p) => [p.id, p]))
  const cards: ScoredPaper[] = []
  for (const entry of edition.papers) {
    const paper = byId.get(entry.id)
    if (!paper) continue
    cards.push({
      ...paper,
      screening_status: entry.screening_status ?? paper.screening_status,
      signal_score: entry.signal_score,
    })
  }

  return (
    <EditionPaperList
      papers={cards}
      runId={edition.run_id}
      logHref={editionHref(edition.date, edition.workspace_id, {
        runId: edition.run_id,
        sub: 'run',
      })}
    />
  )
}

import { AnswerMarkdown } from '@/components/answer-markdown'
import { Breadcrumbs, SectionLabel, StatBand } from '@/components/scanner-ui'
import { StarToggle } from '@/components/star'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
import type { Features } from '@/lib/features'
import type { Lang, T } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import { notFound } from 'next/navigation'
import { editionHref, formatEditionDate } from '../format'
import { EditionPaperList } from './edition-paper-list'

/**
 * One edition's streamed sections. The head needs the edition; the papers
 * need the edition and the scored corpus. Both services are React-cached, so
 * the two sections share one edition fetch. `wsId` is the domain from the
 * URL; without one, the newest edition of the day in any domain is shown.
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
  date,
  lang,
  t,
  domains,
  features,
}: {
  wsId?: string
  date: string
  lang: Lang
  t: T
  /** Domain names by workspace id, for the crumb. */
  domains: Record<string, string>
  /** Required: page.tsx is the only caller, and its skeleton must agree. */
  features: Features
}) {
  const edition = await forPage(briefings.findByDate(date, lang, wsId))
  // A date with no edition is a true 404 — rendered in-stream now that the
  // shell has already gone out (see docs/skeletons.md).
  if (!edition) notFound()

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

/** The papers that passed, as cards with their stars, and the link to the screening log. */
export async function EditionPapers({
  wsId,
  date,
  lang,
}: {
  wsId?: string
  date: string
  lang: Lang
}) {
  const edition = await forPage(briefings.findByDate(date, lang, wsId))
  if (!edition) notFound()
  // The run's own rows: the corpus's, or read live past the snapshot's cap.
  const scored = await forPage(papersService.listRun(edition.workspace_id, edition.run_id))

  const byId = new Map(scored.map((p) => [p.id, p]))
  const cards = edition.papers
    .map((p) => byId.get(p.id))
    .filter((p): p is ScoredPaper => Boolean(p))

  return (
    <EditionPaperList
      papers={cards}
      logHref={editionHref(edition.date, edition.workspace_id, 'run')}
    />
  )
}

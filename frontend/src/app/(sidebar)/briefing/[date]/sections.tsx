import { AnswerMarkdown } from '@/components/answer-markdown'
import { Breadcrumbs, SectionLabel, StatBand } from '@/components/scanner-ui'
import { StarToggle } from '@/components/star'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
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
}: {
  wsId?: string
  date: string
  lang: Lang
  t: T
  /** Domain names by workspace id, for the crumb. */
  domains: Record<string, string>
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
        {/* The briefing's star: right of the title from md up, under it on a
            phone (a flex-1 title never wraps the row). Starred by its run. */}
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between md:gap-6">
          <h1 className="min-w-0 text-[26px]/8 font-semibold tracking-tight text-zinc-950 md:flex-1 dark:text-white">
            {edition.title}
          </h1>
          <StarToggle kind="briefing" id={edition.run_id} className="self-start md:mt-px" />
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
  const scored = await forPage(papersService.listAll(edition.workspace_id))

  const byId = new Map((scored?.papers ?? []).map((p) => [p.id, p]))
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

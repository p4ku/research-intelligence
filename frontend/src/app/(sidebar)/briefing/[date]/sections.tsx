import { AnswerMarkdown } from '@/components/answer-markdown'
import { PaperCard } from '@/components/paper-card'
import { Breadcrumbs, SectionLabel, StatBand } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
import { fmt, type Lang, type T } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { formatEditionDate } from '../format'

/**
 * One edition's streamed sections. The head needs the edition; the papers
 * need the edition and the scored corpus. Both services are React-cached, so
 * the two sections share one edition fetch.
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
}: {
  wsId: string
  date: string
  lang: Lang
  t: T
}) {
  const edition = await forPage(briefings.getByDate(wsId, date, lang))
  // A date with no edition is a true 404 — rendered in-stream now that the
  // shell has already gone out (see docs/skeletons.md).
  if (!edition) notFound()

  const copy = funnelCopy(t)
  const funnel = [
    { value: edition.funnel.fetched, ...copy[0] },
    { value: edition.funnel.passed_screening, ...copy[1] },
    { value: edition.funnel.surfaced, ...copy[2] },
  ]

  return (
    <>
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: t('Briefings'), href: '/briefing' },
            { label: formatEditionDate(edition.date, lang) },
          ]}
          t={t}
        />
        <h1 className="text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
          {edition.title}
        </h1>
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

/** The papers that passed, as cards, with the link to the screening log. */
export async function EditionPapers({
  wsId,
  date,
  lang,
  t,
}: {
  wsId: string
  date: string
  lang: Lang
  t: T
}) {
  const [edition, scored] = await forPage(
    Promise.all([briefings.getByDate(wsId, date, lang), papersService.listAll(wsId)]),
  )
  if (!edition) notFound()

  const byId = new Map((scored?.papers ?? []).map((p) => [p.id, p]))
  const cards = edition.papers
    .map((p) => byId.get(p.id))
    .filter((p): p is ScoredPaper => Boolean(p))

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel size="sm">{t('The papers')}</SectionLabel>
        <span className="flex items-baseline gap-4">
          <span className="font-mono text-[11px] text-zinc-400 tabular-nums dark:text-zinc-500">
            {cards.length === 1 ? t('1 paper') : fmt(t('{n} papers'), { n: cards.length })}
          </span>
          <Link
            href={`/briefing/${edition.date}/run`}
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {t('Screening log →')}
          </Link>
        </span>
      </div>
      <div className="mt-5 space-y-3">
        {cards.map((p) => (
          <PaperCard key={p.id} paper={p} />
        ))}
      </div>
    </section>
  )
}

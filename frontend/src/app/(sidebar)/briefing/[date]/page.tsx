import { AnswerMarkdown } from '@/components/answer-markdown'
import { PaperCard } from '@/components/paper-card'
import { Breadcrumbs, SectionLabel, StatBand } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
import { fmt } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import type { ScoredPaper } from '@/lib/papers/types'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { formatEditionDate } from '../format'

export const dynamic = 'force-dynamic'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ date: string }>
}): Promise<Metadata> {
  const { date } = await params
  const t = await getT()
  return { title: `${t('Briefing')} · ${date}` }
}

// One edition, frozen: the same shape as the dashboard's daily brief — the
// funnel, the brief, the papers that passed — plus the run's screening log.
// Permalinkable, so a briefing can be shared as a URL.

export default async function BriefingEditionPage({
  params,
}: {
  params: Promise<{ date: string }>
}) {
  const [{ date }, ws, t, lang] = await Promise.all([
    params,
    getCurrentWorkspace(),
    getT(),
    getLang(),
  ])
  if (!ws) notFound()
  const [edition, scored] = await forPage(
    Promise.all([briefings.getByDate(ws.id, date, lang), papersService.listAll(ws.id)]),
  )
  if (!edition) notFound()

  const byId = new Map((scored?.papers ?? []).map((p) => [p.id, p]))
  const cards = edition.papers
    .map((p) => byId.get(p.id))
    .filter((p): p is ScoredPaper => Boolean(p))

  const funnel = [
    { value: edition.funnel.fetched, label: t('Screened'), sub: t('matched the focus fields') },
    {
      value: edition.funnel.passed_screening,
      label: t('Included'),
      sub: t('cleared the signal bar'),
    },
    { value: edition.funnel.surfaced, label: t('In the briefing'), sub: t('listed below') },
  ]

  return (
    <div className="space-y-10">
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
    </div>
  )
}

import { Breadcrumbs, SectionLabel, StatBand } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { getLang, getT } from '@/lib/i18n-server'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { formatEditionDate } from '../../format'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Screening log') }
}

// The run behind one edition: the funnel, and what screened out and why.
// Showing the near-misses is the credibility move — the briefing's short list
// means something because the exclusions are inspectable.

export default async function ScreeningLogPage({ params }: { params: Promise<{ date: string }> }) {
  const [{ date }, ws] = await Promise.all([params, getCurrentWorkspace()])
  if (!ws) notFound()
  const edition = await forPage(briefings.getByDate(ws.id, date))
  if (!edition) notFound()

  const t = await getT()
  const lang = await getLang()

  const funnel = [
    { value: edition.funnel.fetched, label: t('Screened'), sub: t('matched the focus fields') },
    {
      value: edition.funnel.passed_screening,
      label: t('Included'),
      sub: t('cleared the signal bar'),
    },
    { value: edition.funnel.surfaced, label: t('In the briefing'), sub: t('passed every gate') },
  ]

  return (
    <div className="space-y-10">
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: t('Briefings'), href: '/briefing' },
            { label: formatEditionDate(edition.date, lang), href: `/briefing/${edition.date}` },
            { label: t('Screening log') },
          ]}
        />
        <h1 className="text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
          {t('Screening log')}
        </h1>
      </div>

      <StatBand items={funnel} flow className="lg:grid-cols-3!" />

      <section>
        <SectionLabel size="sm">{t('Screened out')}</SectionLabel>

        {edition.exclusions.length > 0 ? (
          <table className="mt-5 w-full">
            <thead>
              <tr className="text-left text-xs text-zinc-500 dark:text-zinc-400">
                <th className="pr-6 pb-2 font-medium whitespace-nowrap">{t('Paper')}</th>
                <th className="hidden pr-6 pb-2 font-medium whitespace-nowrap sm:table-cell">
                  {t('Source')}
                </th>
                <th className="pb-2 font-medium whitespace-nowrap">{t('Why it did not pass')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-950/5 dark:divide-white/5">
              {edition.exclusions.map((ex) => (
                <tr key={ex.paper_id} className="align-top">
                  <td className="max-w-xs py-3 pr-6 text-sm font-medium text-zinc-800 dark:text-zinc-100">
                    {ex.title}
                  </td>
                  <td className="hidden py-3 pr-6 text-xs whitespace-nowrap text-zinc-400 sm:table-cell dark:text-zinc-500">
                    {ex.source}
                  </td>
                  <td className="py-3 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
                    {ex.reason ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="mt-5 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">
            {t('Nothing was screened out in this run.')}
          </p>
        )}
      </section>
    </div>
  )
}

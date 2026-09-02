import { SectionLabel, StatBand } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import type { Lang, T } from '@/lib/i18n'
import { notFound } from 'next/navigation'
import { ExclusionsTable } from './exclusions-table'

export function funnelCopy(t: T) {
  return [
    { label: t('Screened'), sub: t('matched the focus fields') },
    { label: t('Included'), sub: t('cleared the signal bar') },
    { label: t('In the briefing'), sub: t('passed every gate') },
  ]
}

/** The run behind one edition: the funnel, and what screened out and why. */
export async function ScreeningLog({
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
  if (!edition) notFound()

  const copy = funnelCopy(t)
  const funnel = [
    { value: edition.funnel.fetched, ...copy[0] },
    { value: edition.funnel.passed_screening, ...copy[1] },
    { value: edition.funnel.surfaced, ...copy[2] },
  ]

  return (
    <>
      <StatBand items={funnel} flow className="lg:grid-cols-3!" />

      <section>
        <SectionLabel size="sm">{t('Screened out')}</SectionLabel>

        {edition.exclusions.length > 0 ? (
          <ExclusionsTable exclusions={edition.exclusions} t={t} />
        ) : (
          <p className="mt-5 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">
            {t('Nothing was screened out in this run.')}
          </p>
        )}
      </section>
    </>
  )
}

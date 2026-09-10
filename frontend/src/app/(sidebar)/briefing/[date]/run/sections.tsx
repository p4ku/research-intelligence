import { SectionLabel, StatBand } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import type { Lang, T } from '@/lib/i18n'
import { notFound } from 'next/navigation'
import { domainEditions, namedElsewhere, SameDayNotice } from '../sections'
import { ExclusionsTable } from './exclusions-table'

export function funnelCopy(t: T) {
  return [{ label: t('Screened') }, { label: t('Analysed') }]
}

/**
 * The run behind one edition: the funnel, and what screened out and why.
 * `wsId` and `runId` are the domain and run from the URL; without them, the
 * day's newest edition.
 */
export async function ScreeningLog({
  wsId,
  runId,
  date,
  lang,
  t,
  domains,
}: {
  wsId?: string
  runId?: string
  date: string
  lang: Lang
  t: T
  /** Domain names by workspace id, for the notice. */
  domains: Record<string, string>
}) {
  const edition = await forPage(briefings.findByDate(date, lang, wsId, runId))
  if (!edition) notFound()
  const editions = await domainEditions(edition, lang)
  const elsewhere = await namedElsewhere(runId, edition, editions, lang)

  const copy = funnelCopy(t)
  const funnel = [
    { value: edition.funnel.fetched, ...copy[0] },
    { value: edition.funnel.passed_screening, ...copy[1] },
  ]

  return (
    <>
      {/* The same line as the edition page: which run this log belongs to,
          when the URL and the day do not say. */}
      <SameDayNotice
        edition={edition}
        editions={editions}
        elsewhere={elsewhere}
        runId={runId}
        sub="run"
        domains={domains}
        t={t}
        lang={lang}
      />
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

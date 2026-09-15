import { SectionLabel, StatBand, type StatBandItem } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import type { Lang, T } from '@/lib/i18n'
import { notFound } from 'next/navigation'
import { formatDay, formatTimestamp, periodLabel } from '../../../dashboard/format'
import { namedElsewhere, StaleLinkNotice } from '../sections'
import { ExclusionsTable } from './exclusions-table'

export function funnelCopy(t: T) {
  return [
    { label: t('Screened') },
    { label: t('Analysed') },
    { label: t('Period covered') },
    { label: t('Generated') },
  ]
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
  const editionPromise = briefings.findByDate(date, lang, wsId, runId, 'excluded')
  const runPromise = runId ? runsService.get(runId).catch(() => null) : null
  const [edition, earlyRun] = await forPage(Promise.all([editionPromise, runPromise]))
  if (!edition) notFound()
  const run = earlyRun ?? (await runsService.get(edition.run_id).catch(() => null))
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

  return (
    <>
      {/* The same line as the edition page: which run this log belongs to,
          when the URL's run is not this one. */}
      <StaleLinkNotice
        edition={edition}
        elsewhere={elsewhere}
        runId={runId}
        sub="run"
        domains={domains}
        t={t}
        lang={lang}
      />
      <StatBand items={funnel} flow />

      <section>
        <SectionLabel size="sm">{t('Screened out')}</SectionLabel>

        {edition.exclusions.length > 0 ? (
          <ExclusionsTable
            exclusions={edition.exclusions}
            t={t}
            runId={run?.id ?? edition.run_id}
            lang={lang}
          />
        ) : (
          <p className="mt-5 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">
            {t('Nothing was screened out in this run.')}
          </p>
        )}
      </section>
    </>
  )
}

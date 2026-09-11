import { Breadcrumbs, SectionLabel, StatBandSkeleton } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import { screeningLogPdfHref } from '@/lib/bff/briefings/href'
import type { Lang, T } from '@/lib/i18n'
import { editionHref, formatEditionDate } from '../../format'
import { ExclusionsTableSkeleton } from './exclusions-table'
import { ExportPdfButton } from './export-button'
import { funnelCopy } from './sections'

/** The log's skeleton: the funnel and the table, one region. */
export function ScreeningLogSkeleton({ t }: { t: T }) {
  const copy = funnelCopy(t)
  return (
    <Skeleton.Region status={t('Loading the screening log')} innerClassName="space-y-10">
      <StatBandSkeleton
        count={2}
        labels={copy.map((c) => c.label)}
        below="none"
        flow
        className="lg:grid-cols-3!"
      />
      <section>
        <SectionLabel size="sm">{t('Screened out')}</SectionLabel>
        <ExclusionsTableSkeleton t={t} />
      </section>
    </Skeleton.Region>
  )
}

/**
 * Crumbs, the static title and the export at its right — real when the date
 * is known; loading.tsx has no date, so its crumb and its export are bones.
 */
export function ScreeningLogHeader({
  t,
  lang,
  date,
  wsId,
  runId,
  domain,
}: {
  t: T
  lang: Lang
  date?: string
  /** The domain (id and display name) and run from the URL; the crumb keeps them. */
  wsId?: string
  runId?: string
  domain?: string
}) {
  const dateLabel = date ? formatEditionDate(date, lang) : null
  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: t('Briefings'), href: '/briefing' },
          date && dateLabel
            ? {
                label: domain ? `${domain} · ${dateLabel}` : dateLabel,
                href: editionHref(date, wsId, { runId }),
              }
            : { label: <Bone.Text widths={['20ch']} /> },
          { label: t('Screening log') },
        ]}
        t={t}
      />
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <h1 className="text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
          {t('Screening log')}
        </h1>
        {date ? (
          <ExportPdfButton href={screeningLogPdfHref(date, wsId, runId)} />
        ) : (
          <Bone.Block className="h-8 w-26 shrink-0" />
        )}
      </div>
    </div>
  )
}

/** The loading.tsx shell. */
export function ScreeningLogPageSkeleton({ t, lang }: { t: T; lang: Lang }) {
  return (
    <div className="space-y-10">
      <ScreeningLogHeader t={t} lang={lang} />
      <ScreeningLogSkeleton t={t} />
    </div>
  )
}

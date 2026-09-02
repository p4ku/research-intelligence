import { Breadcrumbs, SectionLabel, StatBandSkeleton } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import type { Lang, T } from '@/lib/i18n'
import { formatEditionDate } from '../../format'
import { ExclusionsTableSkeleton } from './exclusions-table'
import { funnelCopy } from './sections'

/** The log's skeleton: the funnel and the table, one region. */
export function ScreeningLogSkeleton({ t }: { t: T }) {
  const copy = funnelCopy(t)
  return (
    <Skeleton.Region status={t('Loading the screening log')} innerClassName="space-y-10">
      <StatBandSkeleton
        count={3}
        labels={copy.map((c) => c.label)}
        subs={copy.map((c) => c.sub)}
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

/** Crumbs and the static title — real when the date is known, a bone crumb in loading.tsx. */
export function ScreeningLogHeader({ t, lang, date }: { t: T; lang: Lang; date?: string }) {
  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: t('Briefings'), href: '/briefing' },
          date
            ? { label: formatEditionDate(date, lang), href: `/briefing/${date}` }
            : { label: <Bone.Text widths={['20ch']} /> },
          { label: t('Screening log') },
        ]}
        t={t}
      />
      <h1 className="text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
        {t('Screening log')}
      </h1>
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

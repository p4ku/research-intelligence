import { PageHeader, StatBandSkeleton } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { RunTabsSkeleton } from './run-tabs'
import { RunsTableSkeleton } from './runs-table'

/** Header copy shared by the page and its loading shell. */
export function runsPageCopy(t: T) {
  return {
    title: t('Runs'),
    description: t(
      'Every pipeline run across your domains — what it produced, what it cost, and how long it took.',
    ),
  }
}

/**
 * The runs page's section skeleton — used both by loading.tsx (the whole-page
 * shell on navigation) and as the page's Suspense fallback, so the two are
 * pixel-identical. One Region: one status announcement, one scan sweep. The
 * band's labels are static, so only its numbers are bones; only its third
 * cell carries a sub line in the loaded band, so only that one gets a bone.
 */
export function RunsSectionSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the runs')}>
      <div className="space-y-8">
        <StatBandSkeleton
          count={4}
          labels={[t('Runs'), t('Papers fetched'), t('Passed screening'), t('Total spend')]}
          subs={[null, null, undefined, null]}
        />
        <RunTabsSkeleton t={t} />
        <RunsTableSkeleton t={t} />
      </div>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell — the same static header the page renders. */
export function RunsPageSkeleton({ t }: { t: T }) {
  const copy = runsPageCopy(t)
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Pipeline')} title={copy.title} description={copy.description} />
      <RunsSectionSkeleton t={t} />
    </div>
  )
}

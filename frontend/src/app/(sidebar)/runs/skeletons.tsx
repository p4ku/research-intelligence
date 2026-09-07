import { PageHeader, StatBandSkeleton } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import { RunTabsSkeleton } from './run-tabs'
import { RunsTableSkeleton } from './runs-table'

/** Header copy shared by the page and its loading shell. */
export const runsPageCopy = {
  title: 'Runs',
  description:
    'Every pipeline run in this workspace — what it produced, what it cost, and how long it took.',
}

/**
 * The runs page's section skeleton — used both by loading.tsx (the whole-page
 * shell on navigation) and as the page's Suspense fallback, so the two are
 * pixel-identical. One Region: one status announcement, one scan sweep. The
 * band's labels are static, so only its numbers are bones; only its third
 * cell carries a sub line in the loaded band, so only that one gets a bone.
 */
export function RunsSectionSkeleton() {
  return (
    <Skeleton.Region status="Loading the runs">
      <div className="space-y-8">
        <StatBandSkeleton
          count={4}
          labels={['Runs', 'Papers fetched', 'Passed screening', 'Total spend']}
          subs={[null, null, undefined, null]}
        />
        <RunTabsSkeleton />
        <RunsTableSkeleton />
      </div>
    </Skeleton.Region>
  )
}

/**
 * The loading.tsx shell. The eyebrow is the workspace name on the page, which
 * needs a backend call, so the shell says "Pipeline" the way the page's own
 * no-workspace branch does.
 */
export function RunsPageSkeleton() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Pipeline"
        title={runsPageCopy.title}
        description={runsPageCopy.description}
      />
      <RunsSectionSkeleton />
    </div>
  )
}

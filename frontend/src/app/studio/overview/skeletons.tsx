import { Bone, Skeleton } from '@/components/skeleton'
import { DetailPaneSkeleton } from './detail-pane'
import { RailSkeleton } from './rail'
import { RunListSkeleton } from './run-list'

/** Header copy shared by the page, its notice branch and the loading shell. */
export const overviewCopy = {
  title: 'Overview',
  description:
    'Every run across your workspaces. Scope here is this page’s; the sidebar workspace is unchanged.',
}

/**
 * The whole console as bones — used by loading.tsx on navigation and as the
 * page's Suspense fallback, so the two are identical. One Region: one status
 * sentence, one scan sweep across all three panes. The frame classes mirror
 * command-centre.tsx with a run open, which is how the page usually lands.
 */
export function OverviewSkeleton() {
  return (
    <Skeleton.Region
      status="Loading the overview"
      className="lg:grid lg:h-[calc(100dvh-6rem)] lg:min-h-0 lg:grid-rows-[auto_minmax(0,1fr)]"
      innerClassName="contents"
    >
      <div className="border-line flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b pb-3 lg:pb-2.5">
        <h1 className="text-[22px] leading-7 font-semibold tracking-tight">{overviewCopy.title}</h1>
        <p className="text-muted-foreground text-xs">{overviewCopy.description}</p>
        <p className="ml-auto text-[11.5px] max-sm:w-full">
          <Bone.Text widths={['28ch']} />
        </p>
      </div>
      <div className="wide:grid-cols-[208px_minmax(0,1fr)_400px] wide:grid-rows-[minmax(0,1fr)] lg:max-wide:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:max-wide:grid-rows-[auto_minmax(0,1fr)] lg:grid lg:min-h-0">
        <div className="bg-surface border-line wide:border-r lg:max-wide:col-span-full lg:max-wide:border-b max-lg:hidden">
          <RailSkeleton />
        </div>
        <div className="bg-background lg:border-line lg:min-h-0 lg:overflow-hidden lg:border-r">
          <RunListSkeleton />
        </div>
        <div className="bg-surface max-lg:hidden lg:min-h-0 lg:overflow-hidden">
          <DetailPaneSkeleton />
        </div>
      </div>
    </Skeleton.Region>
  )
}

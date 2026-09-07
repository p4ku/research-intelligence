import {
  Breadcrumbs,
  Card,
  PageHeader,
  SectionLabel,
  StatBandSkeleton,
} from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import { shortId } from '../run-presentation'
import { RunFactsSkeleton } from './run-facts'
import { StepTimelineSkeleton } from './step-timeline'

/**
 * The run page's section skeletons — used both by loading.tsx (the whole-page
 * shell on navigation) and as the page's Suspense fallbacks, so the shell and
 * the streamed state are pixel-identical. One Region per section: one status
 * announcement, one scan sweep.
 */

/**
 * Header, band and facts. The page knows the id from the URL and passes it so
 * the title is real; loading.tsx does not get params, so there it is a bone.
 */
export function RunHeadSkeleton({ id }: { id?: string }) {
  return (
    <Skeleton.Region status="Loading the run">
      <div className="space-y-8">
        <PageHeader
          eyebrow={<Bone.Text widths={['14ch']} />}
          title={
            id ? (
              `Run ${shortId(id)}`
            ) : (
              <>
                Run <Bone.Number digits={8} />
              </>
            )
          }
          description={<Bone.Text widths={['60%']} />}
          actions={<Bone.Chip width={72} />}
        />
        <StatBandSkeleton
          flow
          count={4}
          labels={['Fetched', 'Passed screening', 'Papers stored', 'Extractions']}
          subs={['from the sources', undefined, 'rows in this run', 'parameter values']}
          digits={2}
        />
        <Card>
          <RunFactsSkeleton />
        </Card>
      </div>
    </Skeleton.Region>
  )
}

export function StepsSkeleton() {
  return (
    <Skeleton.Region status="Loading the steps">
      <section className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel>Steps</SectionLabel>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            <Bone.Text widths={['24ch']} />
          </p>
        </div>
        <Card className="py-1">
          <StepTimelineSkeleton />
        </Card>
      </section>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: real crumbs where known, skeleton sections. */
export function RunPageSkeleton({ id }: { id?: string }) {
  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: 'Runs', href: '/runs' },
          { label: id ? shortId(id) : <Bone.Text widths={['8ch']} /> },
        ]}
      />
      <RunHeadSkeleton id={id} />
      <StepsSkeleton />
    </div>
  )
}

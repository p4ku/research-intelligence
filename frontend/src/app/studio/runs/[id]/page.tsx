import { Breadcrumbs } from '@/components/scanner-ui'
import { isUuid } from '@/lib/bff/core/validate'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { shortId } from '../../run-presentation'
import { RunHead, Steps } from './sections'
import { RunHeadSkeleton, StepsSkeleton } from './skeletons'

export const metadata: Metadata = { title: 'Run' }
export const dynamic = 'force-dynamic'

/**
 * The crumbs render with the shell (the id is in the URL); the head — header,
 * band, facts — and the steps stream in behind their own Suspense boundaries,
 * one fetch each. loading.tsx shows the same skeletons on navigation, and the
 * <ViewTransition> pairs animate the skeleton → content handoff.
 *
 * Nothing but `params` is awaited here: a backend call at this level (the
 * workspace, say) would hold the whole shell — crumbs, real-id title, both
 * fallbacks — behind loading.tsx for a round-trip. RunHead fetches the
 * workspace alongside the run, which is the only place it is read.
 */
export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (!isUuid(id)) notFound()

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: 'Studio', href: '/studio/runs' },
          { label: 'Runs', href: '/studio/runs' },
          { label: shortId(id) },
        ]}
      />

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <RunHeadSkeleton id={id} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <RunHead id={id} />
        </ViewTransition>
      </Suspense>

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <StepsSkeleton />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <Steps id={id} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

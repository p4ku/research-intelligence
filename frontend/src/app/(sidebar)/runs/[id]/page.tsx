import { Breadcrumbs } from '@/components/scanner-ui'
import { isUuid } from '@/lib/bff/core/validate'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { shortId } from '../run-presentation'
import { RunHead, Steps } from './sections'
import { RunHeadSkeleton, StepsSkeleton } from './skeletons'

export const metadata: Metadata = { title: 'Run' }
export const dynamic = 'force-dynamic'

/**
 * The crumbs render with the shell (the id is in the URL); the head — header,
 * band, facts — and the steps stream in behind their own Suspense boundaries,
 * one fetch each. loading.tsx shows the same skeletons on navigation, and the
 * <ViewTransition> pairs animate the skeleton → content handoff.
 */
export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, workspace] = await Promise.all([params, getCurrentWorkspace()])
  if (!isUuid(id)) notFound()

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: 'Runs', href: '/runs' }, { label: shortId(id) }]} />

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <RunHeadSkeleton id={id} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <RunHead id={id} workspace={workspace} />
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

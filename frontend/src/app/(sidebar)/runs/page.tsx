import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { tabFrom } from './run-tabs'
import { RunsSection } from './sections'
import { RunsSectionSkeleton, runsPageCopy } from './skeletons'

export const metadata: Metadata = { title: 'Runs' }
export const dynamic = 'force-dynamic'

/**
 * The header renders with the shell; the band, filter strip and table stream
 * in behind one Suspense boundary (they all read the same list, every run
 * across the user's domains). loading.tsx shows the same skeleton on
 * navigation, and the <ViewTransition> pair animates the skeleton → content
 * handoff (bone-exit/bone-enter in styles/tailwind.css); default="none" keeps
 * it quiet for every other transition.
 */
export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>
}) {
  const [{ status }, state] = await Promise.all([searchParams, getWorkspacesState()])
  const tab = tabFrom(status)

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Pipeline"
        title={runsPageCopy.title}
        description={runsPageCopy.description}
      />

      {state.kind !== 'ok' ? (
        <WorkspaceNotice kind={state.kind} english />
      ) : (
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <RunsSectionSkeleton />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <RunsSection tab={tab} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

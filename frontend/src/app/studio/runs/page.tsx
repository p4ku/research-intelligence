import { Card, PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getWorkspaceState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { tabFrom } from './run-tabs'
import { RunsSection } from './sections'
import { RunsSectionSkeleton, runsPageCopy } from './skeletons'

export const metadata: Metadata = { title: 'Runs' }
export const dynamic = 'force-dynamic'

/**
 * The header renders with the shell; the band, filter strip and table stream
 * in behind one Suspense boundary (they all read the same list). loading.tsx
 * shows the same skeleton on navigation, and the <ViewTransition> pair
 * animates the skeleton → content handoff (bone-exit/bone-enter in
 * styles/tailwind.css); default="none" keeps it quiet for every other
 * transition.
 */
export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>
}) {
  const [{ status }, state] = await Promise.all([searchParams, getWorkspaceState()])
  const tab = tabFrom(status)

  if (state.kind !== 'ok') {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow="Studio" title={runsPageCopy.title} />
        {state.kind === 'unavailable' ? (
          <WorkspaceNotice kind="unavailable" english />
        ) : (
          <Card>
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
              No workspace selected
            </p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Pick a workspace to review its pipeline runs.
            </p>
          </Card>
        )}
      </div>
    )
  }
  const ws = state.ws

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={ws.name}
        title={runsPageCopy.title}
        description={runsPageCopy.description}
      />

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <RunsSectionSkeleton />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <RunsSection wsId={ws.id} wsName={ws.name} tab={tab} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

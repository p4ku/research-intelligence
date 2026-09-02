import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getWorkspaceState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { OverviewSection } from './sections'
import { overviewCopy, OverviewSkeleton } from './skeletons'

export const metadata: Metadata = { title: 'Overview' }
export const dynamic = 'force-dynamic'

/**
 * The Studio overview: every run across every workspace, with the run that
 * needs attention open beside the list. The console streams in behind one
 * Suspense boundary; loading.tsx shows the same skeleton on navigation, and
 * the <ViewTransition> pair animates the handoff (bone-exit/bone-enter in
 * styles/tailwind.css). Scope, open run and filter ride in the URL
 * (`?ws=`, `?run=`, `?status=`) and never touch the sidebar's workspace.
 */
export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ ws?: string; run?: string; status?: string }>
}) {
  const [{ ws, run, status }, state] = await Promise.all([searchParams, getWorkspaceState()])

  if (state.kind !== 'ok') {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow="Studio" title={overviewCopy.title} />
        <WorkspaceNotice kind={state.kind} english />
      </div>
    )
  }

  return (
    <Suspense
      fallback={
        <ViewTransition exit="bone-exit" default="none">
          <OverviewSkeleton />
        </ViewTransition>
      }
    >
      <ViewTransition enter="bone-enter" default="none">
        <OverviewSection ws={ws} run={run} status={status} currentWorkspaceId={state.ws.id} />
      </ViewTransition>
    </Suspense>
  )
}

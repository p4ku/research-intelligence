import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { AskSection } from './sections'
import { AskConsoleSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Ask the scanner') }
}

/**
 * The header renders with the shell; the console — which needs the corpus
 * for its picker and the session history for its rail — streams in behind
 * one Suspense boundary. loading.tsx shows the same skeleton on navigation,
 * and the <ViewTransition> pair animates the handoff.
 */
export default async function AskPage({
  searchParams,
}: {
  searchParams: Promise<{ paper?: string; session?: string }>
}) {
  const [t, state, { paper, session }] = await Promise.all([
    getT(),
    getWorkspacesState(),
    searchParams,
  ])

  if (state.kind !== 'ok') {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Assistant')} title={t('Ask Research Intelligence')} />
        <WorkspaceNotice kind={state.kind} />
      </div>
    )
  }
  // The console owns the viewport: the page does not scroll, the transcript does.
  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col gap-6 lg:h-[calc(100dvh-6rem)]">
      <div className="shrink-0">
        <PageHeader eyebrow={t('Assistant')} title={t('Ask Research Intelligence')} />
      </div>
      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <AskConsoleSkeleton t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <AskSection paper={paper} session={session} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

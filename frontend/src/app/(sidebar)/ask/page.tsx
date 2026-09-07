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
 * The canvas is the page: no page header competing with the chat's own top
 * bar, just a screen-reader h1 so the document still has one. The console —
 * which needs the corpus for its picker and the session history for its
 * sidecar — streams in behind one Suspense boundary. loading.tsx shows the
 * same skeleton on navigation, and the <ViewTransition> pair animates the
 * handoff.
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
  // The canvas owns the viewport: the page does not scroll, the transcript does.
  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col lg:h-[calc(100dvh-3.5rem)]">
      <h1 className="sr-only">{t('Ask Research Intelligence')}</h1>
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

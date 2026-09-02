import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspaceState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { EditionsSection } from './sections'
import { EditionsSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Briefings') }
}

// /briefing is the archive as a reading room: the dashboard carries today's
// briefing, and every edition lives here — search on top, the selected brief
// on the left, the history rail on the right. One edition per completed
// pipeline run; each has a permalink at /briefing/[date].
//
// The header renders with the shell; the reading room streams in behind one
// Suspense boundary (one list feeds search, reader and rail). loading.tsx
// shows the same skeleton on navigation.

export default async function BriefingPage() {
  const [t, lang, state] = await Promise.all([getT(), getLang(), getWorkspaceState()])

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Daily briefings')} title={t('Briefings')} />
      {state.kind !== 'ok' ? (
        <WorkspaceNotice state={state} />
      ) : (
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <EditionsSkeleton t={t} />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <EditionsSection wsId={state.ws.id} lang={lang} t={t} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

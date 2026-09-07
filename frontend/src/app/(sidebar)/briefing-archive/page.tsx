import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getFeatures } from '@/lib/features-server'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { EditionsSection } from './sections'
import { EditionsSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Briefings') }
}

// /briefing-archive is the reading room that was /briefing until the spec's
// ledger replaced it (7 Sep 2026): search on top, the selected brief on the
// left, the history rail on the right. Kept, reachable by URL only, so the
// old view can be restored by swapping the folders back; delete it once the
// ledger has settled.
//
// The header renders with the shell; the reading room streams in behind one
// Suspense boundary. loading.tsx shows the same skeleton on navigation.

export default async function BriefingArchivePage() {
  const [t, lang, state, features] = await Promise.all([
    getT(),
    getLang(),
    getWorkspacesState(),
    getFeatures(),
  ])

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Daily briefings')} title={t('Briefings')} />
      {state.kind !== 'ok' ? (
        <WorkspaceNotice kind={state.kind} />
      ) : (
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <EditionsSkeleton t={t} features={features} />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <EditionsSection workspaces={state.all} lang={lang} t={t} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

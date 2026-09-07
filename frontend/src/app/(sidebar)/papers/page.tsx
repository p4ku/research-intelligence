import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { PapersSection } from './sections'
import { PapersSkeletonRegion } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Papers') }
}

/**
 * Every paper from every domain the user belongs to, one browser over all of
 * them. `?q=` is Home's search, pre-filled into the browser's field.
 *
 * The header renders with the shell; the browser streams in behind one
 * Suspense boundary. loading.tsx shows the same skeleton on navigation, and
 * the <ViewTransition> pair animates the handoff.
 */
export default async function PapersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>
}) {
  const [t, state, { q }] = await Promise.all([getT(), getWorkspacesState(), searchParams])
  // One domain reads as itself; several read as the whole corpus, with the
  // domain filter in the browser doing the narrowing.
  const eyebrow =
    state.kind === 'ok' && state.all.length === 1 ? state.all[0].name : t('All domains')

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={state.kind === 'ok' ? eyebrow : t('Corpus')} title={t('Papers')} />
      {state.kind !== 'ok' ? (
        <WorkspaceNotice kind={state.kind} />
      ) : (
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <PapersSkeletonRegion t={t} />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <PapersSection t={t} q={q} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

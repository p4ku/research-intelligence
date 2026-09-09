import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { tabFrom } from './run-tabs'
import { RunsSection } from './sections'
import { RunsSectionSkeleton, runsPageCopy } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  // generateMetadata runs independently of the page body, so it reads the
  // language cookie itself; otherwise the tab and the history entry would stay
  // English while the page is German.
  const t = await getT()
  return { title: t('Runs') }
}

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
  const [{ status }, state, t, lang] = await Promise.all([
    searchParams,
    getWorkspacesState(),
    getT(),
    getLang(),
  ])
  const tab = tabFrom(status)
  const copy = runsPageCopy(t)

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Pipeline')} title={copy.title} description={copy.description} />

      {state.kind !== 'ok' ? (
        <WorkspaceNotice kind={state.kind} />
      ) : (
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <RunsSectionSkeleton t={t} />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <RunsSection tab={tab} t={t} lang={lang} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

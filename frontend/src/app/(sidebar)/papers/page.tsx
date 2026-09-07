import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getFeatures, hasFeature, requireFeature } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { stateFrom } from '@/lib/papers/browse'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { PapersSection } from './sections'
import { PapersSkeletonRegion } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  // generateMetadata runs independently of the page body, so it needs its own
  // gate: without it the 404's tab and history entry would still read "Papers".
  if (!(await hasFeature('all_papers'))) return {}
  const t = await getT()
  return { title: t('Papers') }
}

/**
 * Every paper from every domain the user belongs to, one browser over all of
 * them, a page at a time. The URL carries the browser's whole state (filters,
 * sort, search, page — src/lib/papers/browse.ts); the server renders the page
 * it names and the browser fetches the rest. `?q=` is Home's search handing
 * over.
 *

 * The header renders with the shell; the browser streams in behind one
 * Suspense boundary. loading.tsx shows the same skeleton on navigation, and
 * the <ViewTransition> pair animates the handoff.
 *
 * Behind the `all_papers` demo flag: off, the route does not exist. The gate is
 * the first statement, above the workspace check, so a hidden page is gone
 * even during an outage. Because the route has a loading.tsx, Next streams the
 * shell with HTTP 200 and renders the not-found card in place (the same shape
 * as /ask and a dead paper permalink); loading.tsx returns null when the flag
 * is off so no Papers skeleton paints first.
 */
export default async function PapersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  await requireFeature('all_papers')
  const [t, state, params, features] = await Promise.all([
    getT(),
    getWorkspacesState(),
    searchParams,
    getFeatures(),
  ])
  // One domain reads as itself; several read as the whole corpus, with the
  // domain filter in the browser doing the narrowing.
  const eyebrow =
    state.kind === 'ok' && state.all.length === 1 ? state.all[0].name : t('All domains')
  const domains = state.kind === 'ok' ? state.all.map(({ id, name }) => ({ id, name })) : []
  const browse = stateFrom(params, domains)
  // The same forcing the browser applies: with stars off, `?starred=1` narrows
  // nothing — and server and client must agree, or the first paint refetches.
  if (!features.stars) browse.starred = false

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
            <PapersSection t={t} state={browse} domains={domains} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

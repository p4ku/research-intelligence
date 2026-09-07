import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { hasFeature, requireFeature } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { AskSection } from './sections'
import { AskConsoleSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  // Hidden by the `ask` demo flag: no title, or the tab advertises a route
  // that answers the not-found card. The root default stands instead.
  if (!(await hasFeature('ask'))) return {}
  const t = await getT()
  return { title: t('Ask the scanner') }
}

/**
 * The canvas is the page: no page header competing with the chat's own top
 * bar, just a screen-reader h1 so the document still has one. The console
 * paints with nothing fetched — the corpus and the history follow after
 * mount — so the Suspense boundary only ever shows for a `?paper=` deep
 * link, whose one scorecard read resolves the chip. loading.tsx shows the
 * same skeleton on navigation, and the <ViewTransition> pair animates the
 * handoff.
 *
 * The `ask` demo flag is checked at the top of the body, before the
 * workspace round-trip: off means the route does not exist, whatever the
 * query string carries.
 */
export default async function AskPage({
  searchParams,
}: {
  searchParams: Promise<{ paper?: string; session?: string; q?: string }>
}) {
  await requireFeature('ask')
  const [t, state, { paper, session, q }] = await Promise.all([
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
  // The canvas owns the viewport: `data-canvas` asks the shell for it (see
  // sidebar-layout.tsx), so the page does not scroll — the transcript does.
  return (
    <div data-canvas className="flex min-h-0 flex-1 flex-col">
      <h1 className="sr-only">{t('Ask Research Intelligence')}</h1>
      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <AskConsoleSkeleton t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <AskSection paper={paper} session={session} question={q} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

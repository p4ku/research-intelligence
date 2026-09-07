import { CorpusSearch } from '@/components/corpus-search/corpus-search'
import { scanTopics } from '@/components/corpus-search/topics'
import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getSessionUser } from '@/lib/auth/session'
import { fmt } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { LedgerSection, MastheadSection } from './sections'
import { LedgerSkeletonRegion, MastheadSkeletonRegion } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Home') }
}

/**
 * Home: the search across every paper, the Current briefing read first (the
 * masthead), then Recent Briefings beside Start New Briefing. The shell —
 * header, search — renders immediately; the masthead and the ledger grid
 * stream in behind their own Suspense boundaries, and loading.tsx shows the
 * same skeletons on navigation. <ViewTransition> pairs animate the
 * skeleton → content handoff (bone-exit/bone-enter in styles/tailwind.css);
 * default="none" keeps them quiet during every other transition.
 */
export default async function DashboardPage() {
  const [user, state, t, lang] = await Promise.all([
    getSessionUser(),
    getWorkspacesState(),
    getT(),
    getLang(),
  ])
  const name = user?.name.split(' ')[0] || t('there')
  const header = <PageHeader eyebrow={t('Home')} title={fmt(t('Good morning, {name}'), { name })} />

  if (state.kind !== 'ok') {
    // An outage is not an empty Home, and no domain means nothing to read
    // or to run: the notice says which, with Retry for the outage.
    return (
      <div className="space-y-8">
        {header}
        <WorkspaceNotice kind={state.kind} />
      </div>
    )
  }

  const domains = state.all.map((w) => ({ id: w.id, name: w.name }))
  // The form's "To" defaults to today; the server's day, so the first
  // client render agrees with the HTML it hydrates.
  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="space-y-8">
      {header}
      <CorpusSearch domains={domains} suggestions={scanTopics(state.all)} />

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <MastheadSkeletonRegion t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <MastheadSection t={t} lang={lang} />
        </ViewTransition>
      </Suspense>

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <LedgerSkeletonRegion t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <LedgerSection t={t} lang={lang} domains={domains} today={today} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

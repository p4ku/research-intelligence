import { CorpusSearch } from '@/components/corpus-search/corpus-search'
import { scanTopics } from '@/components/corpus-search/topics'
import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getSessionUser } from '@/lib/auth/session'
import { getFeatures } from '@/lib/features-server'
import { fmt } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { LedgerSection } from './sections'
import { LedgerSkeletonRegion } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Home') }
}

/**
 * Home: the search across every paper, then Recent Briefings beside Start
 * New Briefing. The shell — header, search — renders immediately; the
 * ledger grid streams in behind its Suspense boundary, and loading.tsx
 * shows the same skeleton on navigation. <ViewTransition> pairs animate the
 * skeleton → content handoff (bone-exit/bone-enter in styles/tailwind.css);
 * default="none" keeps them quiet during every other transition.
 *
 * The Current briefing's masthead (7 Sep 2026) is hidden from Home: the
 * ledger's Current row unfolds the same brief and top papers behind its
 * triangle, and a click on the row opens the briefing, so the page opens
 * on the table. `Masthead` itself stays in masthead.tsx for the Studio
 * skeleton gallery.
 *
 * The search is the corpus typeahead: every row it offers is a /papers
 * destination, so `all_papers` off removes the whole panel rather than
 * leaving a field with nowhere to go — and with it Home's Ask row.
 * dashboard/skeletons.tsx must make the same call or the shell paints a
 * search that then vanishes.
 */
export default async function DashboardPage() {
  const [user, state, t, lang, features] = await Promise.all([
    getSessionUser(),
    getWorkspacesState(),
    getT(),
    getLang(),
    getFeatures(),
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
      {features.all_papers && (
        <CorpusSearch domains={domains} suggestions={scanTopics(state.all)} />
      )}

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <LedgerSkeletonRegion t={t} features={features} />
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

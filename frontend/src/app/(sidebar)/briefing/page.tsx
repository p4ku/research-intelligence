import { PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getFeatures } from '@/lib/features-server'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Suspense, ViewTransition } from 'react'
import { LedgerSection } from './sections'
import { LedgerSkeletonRegion } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Briefings') }
}

// /briefing is the archive of every completed briefing — the spec's ledger:
// domain, period, generated, screened, included; the Current one highlighted;
// a domain filter, a star per row, twenty a page. Each row opens to its brief
// and leads to /briefing/[date]?domain=. Filter and page ride in the URL,
// read by the ledger itself (useSearchParams), so this page ignores them.
//
// The header renders with the shell; the ledger streams in behind one
// Suspense boundary. loading.tsx shows the same skeleton on navigation.
// The reading room this replaced lives on at /briefing-archive.

export default async function BriefingsPage() {
  const [t, lang, state, features] = await Promise.all([
    getT(),
    getLang(),
    getWorkspacesState(),
    getFeatures(),
  ])

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Briefings archive')} title={t('Briefings')} />
      {state.kind !== 'ok' ? (
        <WorkspaceNotice kind={state.kind} />
      ) : (
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <LedgerSkeletonRegion
                t={t}
                domains={state.all.map((ws) => ws.name)}
                features={features}
              />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <LedgerSection workspaces={state.all} lang={lang} t={t} />
          </ViewTransition>
        </Suspense>
      )}
    </div>
  )
}

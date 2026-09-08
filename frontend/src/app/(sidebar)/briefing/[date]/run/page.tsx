import { WorkspaceNotice } from '@/components/workspace-notice'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { isEditionDate } from '../../format'
import { domainNames, domainScope, runScope } from '../../scope'
import { ScreeningLog } from './sections'
import { ScreeningLogHeader, ScreeningLogSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Screening log') }
}

// The run behind one edition: the funnel, and what screened out and why.
// Showing the near-misses is the credibility move — the briefing's short list
// means something because the exclusions are inspectable.
//
// Crumbs and title render with the shell (the date, domain and run are in
// the URL); the funnel and the table stream behind one boundary. loading.tsx
// shows the same skeleton on navigation.

export default async function ScreeningLogPage({
  params,
  searchParams,
}: {
  params: Promise<{ date: string }>
  searchParams: Promise<{ domain?: string; run?: string }>
}) {
  const [{ date }, { domain, run }, state, t, lang] = await Promise.all([
    params,
    searchParams,
    getWorkspacesState(),
    getT(),
    getLang(),
  ])
  // Same split as the edition page: only a date with no edition is a 404.
  if (state.kind !== 'ok') return <WorkspaceNotice kind={state.kind} />
  if (!isEditionDate(date)) notFound()
  const wsId = domainScope(state.all, domain)
  const runId = runScope(run)
  const domains = domainNames(state.all)

  return (
    <div className="space-y-10">
      <ScreeningLogHeader
        t={t}
        lang={lang}
        date={date}
        wsId={wsId}
        runId={runId}
        domain={wsId && domains[wsId]}
      />

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <ScreeningLogSkeleton t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <ScreeningLog wsId={wsId} runId={runId} date={date} lang={lang} t={t} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

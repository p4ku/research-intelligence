import { WorkspaceNotice } from '@/components/workspace-notice'
import { getFeatures } from '@/lib/features-server'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { isEditionDate } from '../format'
import { domainNames, domainScope, runScope } from '../scope'
import { EditionHead, EditionPapers } from './sections'
import { EditionHeadSkeleton, EditionPapersSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ date: string }>
}): Promise<Metadata> {
  const { date } = await params
  const t = await getT()
  return { title: `${t('Briefing')} · ${date}` }
}

// One edition, frozen: the same shape as the dashboard's daily brief — the
// funnel, the brief, the papers that passed — plus the run's screening log.
// Permalinkable, so a briefing can be shared as a URL: the day, the domain
// that produced it (two domains can complete a run on the same day) and the
// run (one domain can complete two runs on the same day).
//
// Two sections stream behind their own boundaries: the head on the edition,
// the papers on the edition plus the scored corpus. loading.tsx shows the same
// skeletons on navigation.

export default async function BriefingEditionPage({
  params,
  searchParams,
}: {
  params: Promise<{ date: string }>
  searchParams: Promise<{ domain?: string; run?: string }>
}) {
  const [{ date }, { domain, run }, state, t, lang, features] = await Promise.all([
    params,
    searchParams,
    getWorkspacesState(),
    getT(),
    getLang(),
    getFeatures(),
  ])
  // A missing domain list is not a missing page: an outage gets the honest
  // notice, a user with no membership gets the membership copy — only a
  // date with no edition (or not a date at all) is a true 404.
  if (state.kind !== 'ok') return <WorkspaceNotice kind={state.kind} />
  if (!isEditionDate(date)) notFound()
  const wsId = domainScope(state.all, domain)
  const runId = runScope(run)
  const domains = domainNames(state.all)

  return (
    <div className="space-y-10">
      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <EditionHeadSkeleton
              t={t}
              lang={lang}
              date={date}
              domain={wsId && domains[wsId]}
              features={features}
            />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <EditionHead
            wsId={wsId}
            runId={runId}
            date={date}
            lang={lang}
            t={t}
            domains={domains}
            features={features}
          />
        </ViewTransition>
      </Suspense>

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <EditionPapersSkeleton
              t={t}
              date={date}
              wsId={wsId}
              runId={runId}
              features={features}
            />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <EditionPapers wsId={wsId} runId={runId} date={date} lang={lang} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

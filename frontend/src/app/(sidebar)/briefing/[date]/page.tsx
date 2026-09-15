import { WorkspaceNotice } from '@/components/workspace-notice'
import { getFeatures } from '@/lib/features-server'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { formatEditionDate, isEditionDate } from '../format'
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
  const [t, lang] = await Promise.all([getT(), getLang()])
  // The reader's date, not the URL's: "Freitag, 3. Juli 2026", never "2026-07-03".
  return {
    title: `${t('Briefing')} · ${isEditionDate(date) ? formatEditionDate(date, lang) : date}`,
  }
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
  searchParams: Promise<{
    domain?: string
    run?: string
    page?: string
    score?: string
    sort?: string
  }>
}) {
  const [
    { date },
    { domain, run, page: pageStr, score: scoreStr, sort: sortStr },
    state,
    t,
    lang,
    features,
  ] = await Promise.all([
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
  const page = pageStr && /^[1-9]\d*$/.test(pageStr) ? Number(pageStr) : 1
  const minScore = scoreStr && /^\d+$/.test(scoreStr) ? Number(scoreStr) : undefined
  const sort = sortStr && /^(score|published|dim:\S{1,120})$/.test(sortStr) ? sortStr : undefined

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
            page={page}
            minScore={minScore}
            sort={sort}
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
          <EditionPapers
            wsId={wsId}
            runId={runId}
            date={date}
            lang={lang}
            page={page}
            minScore={minScore}
            sort={sort}
          />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

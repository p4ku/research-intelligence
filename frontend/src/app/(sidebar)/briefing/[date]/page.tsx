import { WorkspaceNotice } from '@/components/workspace-notice'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspaceState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { isEditionDate } from '../format'
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
// Permalinkable, so a briefing can be shared as a URL.
//
// Two sections stream behind their own boundaries: the head on the edition,
// the papers on the edition plus the scored corpus. loading.tsx shows the same
// skeletons on navigation.

export default async function BriefingEditionPage({
  params,
}: {
  params: Promise<{ date: string }>
}) {
  const [{ date }, state, t, lang] = await Promise.all([
    params,
    getWorkspaceState(),
    getT(),
    getLang(),
  ])
  // A missing workspace is not a missing page: an outage gets the honest
  // notice, a user with no membership gets the membership copy — only a
  // date with no edition (or not a date at all) is a true 404.
  if (state.kind !== 'ok') return <WorkspaceNotice kind={state.kind} />
  if (!isEditionDate(date)) notFound()
  const ws = state.ws

  return (
    <div className="space-y-10">
      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <EditionHeadSkeleton t={t} lang={lang} date={date} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <EditionHead wsId={ws.id} date={date} lang={lang} t={t} />
        </ViewTransition>
      </Suspense>

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <EditionPapersSkeleton t={t} date={date} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <EditionPapers wsId={ws.id} date={date} lang={lang} t={t} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

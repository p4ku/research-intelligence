import { Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { SectionAnchors } from '@/components/top-bar'
import { getSessionUser } from '@/lib/auth/session'
import { fmt } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import Link from 'next/link'
import { Suspense, ViewTransition } from 'react'
import { funnelCopy } from './data'
import { Brief, BriefLink, Funnel, Papers, TodayEyebrow } from './sections'
import { BriefSkeleton, FunnelSkeleton, PapersSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

const anchors = [
  { id: 'today', label: 'Today in brief' },
  { id: 'the-papers', label: 'The papers' },
]

/**
 * The dashboard streams in three sections (funnel, brief, papers), each its
 * own Suspense boundary over ./sections. The shell — header, section labels,
 * anchors — renders immediately; loading.tsx shows the same skeletons on
 * navigation. <ViewTransition> pairs animate the skeleton → content handoff
 * (bone-exit/bone-enter in styles/tailwind.css); default="none" keeps them
 * quiet during every other transition, including RunPapers' sort transitions.
 */
export default async function DashboardPage() {
  const [user, ws, t, lang] = await Promise.all([
    getSessionUser(),
    getCurrentWorkspace(),
    getT(),
    getLang(),
  ])
  const name = user?.name.split(' ')[0] || t('there')

  if (!ws) {
    // No workspace: nothing to fetch, so no boundaries — the page renders in
    // one pass with the same copy as before.
    const funnel = funnelCopy(t).map((c) => ({ value: 0, ...c }))
    return (
      <div className="space-y-10">
        <SectionAnchors anchors={anchors} />
        <PageHeader eyebrow={t('Today')} title={fmt(t('Good morning, {name}'), { name })} />
        <section id="today" className="scroll-mt-28">
          <StatBand items={funnel} flow className="lg:grid-cols-3!" />
          <div className="mt-8">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <SectionLabel size="sm">{t('Today in brief')}</SectionLabel>
            </div>
            <p className="mt-4 max-w-3xl text-base leading-relaxed text-pretty text-zinc-600 dark:text-zinc-300">
              {t('No workspace selected')}
            </p>
          </div>
        </section>
        <section id="the-papers" className="scroll-mt-28">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <SectionLabel size="sm">{t('The papers')}</SectionLabel>
            <Link
              href="/papers"
              className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
            >
              {t('All papers →')}
            </Link>
          </div>
          <div className="mt-5">
            <Card>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t(
                  'You are not a member of any workspace yet. Membership is managed in the backend.',
                )}
              </p>
            </Card>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="space-y-10">
      <SectionAnchors anchors={anchors} />

      <PageHeader
        eyebrow={
          <Suspense fallback={t('Today')}>
            <TodayEyebrow wsId={ws.id} t={t} lang={lang} />
          </Suspense>
        }
        title={fmt(t('Good morning, {name}'), { name })}
        actions={
          <span className="bg-accent inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-[11px] font-medium text-white">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-white/80" />
            {ws.name}
          </span>
        }
      />

      {/* ------------------------------ Today in brief ---------------------------- */}
      <section id="today" className="scroll-mt-28">
        <Suspense
          fallback={
            <ViewTransition exit="bone-exit" default="none">
              <FunnelSkeleton t={t} />
            </ViewTransition>
          }
        >
          <ViewTransition enter="bone-enter" default="none">
            <Funnel wsId={ws.id} t={t} />
          </ViewTransition>
        </Suspense>
        <div className="mt-8">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <SectionLabel size="sm">{t('Today in brief')}</SectionLabel>
            <Suspense fallback={null}>
              <BriefLink wsId={ws.id} t={t} />
            </Suspense>
          </div>
          <Suspense
            fallback={
              <ViewTransition exit="bone-exit" default="none">
                <BriefSkeleton t={t} />
              </ViewTransition>
            }
          >
            <ViewTransition enter="bone-enter" default="none">
              <Brief wsId={ws.id} t={t} />
            </ViewTransition>
          </Suspense>
        </div>
      </section>

      {/* -------------------------------- The papers ------------------------------ */}
      <section id="the-papers" className="scroll-mt-28">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel size="sm">{t('The papers')}</SectionLabel>
          <Link
            href="/papers"
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {t('All papers →')}
          </Link>
        </div>
        <div className="mt-5">
          <Suspense
            fallback={
              <ViewTransition exit="bone-exit" default="none">
                <PapersSkeleton t={t} />
              </ViewTransition>
            }
          >
            <ViewTransition enter="bone-enter" default="none">
              <Papers wsId={ws.id} t={t} />
            </ViewTransition>
          </Suspense>
        </div>
      </section>
    </div>
  )
}

import { Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { SectionAnchors } from '@/components/top-bar'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { getSessionUser } from '@/lib/auth/session'
import { fmt } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import Link from 'next/link'
import { Suspense, ViewTransition } from 'react'
import { funnelCopy } from './data'
import { Brief, BriefLink, Funnel, Papers, TodayDomain, TodayEyebrow } from './sections'
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
 * "Today" is the newest completed run in any of the user's domains.
 */
export default async function DashboardPage() {
  const [user, state, t, lang] = await Promise.all([
    getSessionUser(),
    getWorkspacesState(),
    getT(),
    getLang(),
  ])
  const name = user?.name.split(' ')[0] || t('there')

  if (state.kind === 'unavailable') {
    // An outage is not a zero-paper day: no zeroed stats, no membership copy.
    return (
      <div className="space-y-10">
        <PageHeader eyebrow={t('Today')} title={fmt(t('Good morning, {name}'), { name })} />
        <WorkspaceNotice kind="unavailable" />
      </div>
    )
  }

  if (state.kind === 'none') {
    // No domain to read from: nothing to fetch, so no boundaries — the page
    // renders in one pass with the membership copy.
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
              {t('No domains yet')}
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
                {t("You don't have access to any domain yet. Ask an administrator for access.")}
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
            <TodayEyebrow t={t} lang={lang} />
          </Suspense>
        }
        title={fmt(t('Good morning, {name}'), { name })}
        actions={
          // The badge needs the latest run, so it streams; the skeleton shows
          // no actions, and neither does this until the run is known.
          <Suspense fallback={null}>
            <TodayDomain />
          </Suspense>
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
            <Funnel t={t} />
          </ViewTransition>
        </Suspense>
        <div className="mt-8">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <SectionLabel size="sm">{t('Today in brief')}</SectionLabel>
            <Suspense fallback={null}>
              <BriefLink t={t} lang={lang} />
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
              <Brief t={t} lang={lang} />
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
              <Papers t={t} />
            </ViewTransition>
          </Suspense>
        </div>
      </section>
    </div>
  )
}

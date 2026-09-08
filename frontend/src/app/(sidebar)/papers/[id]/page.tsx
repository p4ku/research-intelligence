import { Breadcrumbs } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { forPage } from '@/lib/bff/core/page'
import { isUuid } from '@/lib/bff/core/validate'
import { papers } from '@/lib/bff/papers/service'
import { getFeatures } from '@/lib/features-server'
import { getLang, getT } from '@/lib/i18n-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { runScope } from '../../briefing/scope'
import { PaperCrumb, PaperRecord, RunCrumbs } from './sections'
import { PaperRecordSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  const result = isUuid(id) ? await forPage(papers.get(id)) : null
  return { title: result ? result.paper.title : 'Paper' }
}

/**
 * The crumbs render with the shell (the title crumb streams in on its own);
 * the record — header, signal card, dimensions, screening, abstract, files
 * and the chat rail — streams behind one Suspense boundary, since all of it
 * comes from the one `papers.get`. loading.tsx shows the same skeleton on
 * navigation, and the <ViewTransition> pair animates the handoff.
 *
 * `?run=` names the briefing the paper was opened from. The page then shows
 * the paper as that run read it, the crumb trail leads back through the
 * edition, and the pager walks the edition's papers — see sections.tsx.
 * Without it the page is the paper as it stands today.
 *
 * Detail is NOT behind `all_papers` — it is reached from briefings, Home and
 * chat citations — but everything on it that is derived from the list is: with
 * the flag off the whole crumb trail goes (a one-item trail whose only label
 * can be null renders an empty bar) and PaperNav loses its pager. A briefing
 * trail is derived from the briefing, not the list, so it shows regardless.
 */
export default async function PaperDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ run?: string }>
}) {
  const [{ id }, { run }, t, lang, features] = await Promise.all([
    params,
    searchParams,
    getT(),
    getLang(),
    getFeatures(),
  ])
  if (!isUuid(id)) notFound()
  const runId = runScope(run)

  return (
    <div className="mx-auto max-w-7xl">
      {runId ? (
        <Suspense
          fallback={
            <Breadcrumbs
              items={[
                { label: t('Briefings'), href: '/briefing' },
                { label: <Bone.Text widths={['24ch']} /> },
                { label: <Bone.Text widths={['28ch']} /> },
              ]}
              t={t}
            />
          }
        >
          <RunCrumbs id={id} runId={runId} t={t} lang={lang} features={features} />
        </Suspense>
      ) : (
        features.all_papers && (
          <Breadcrumbs
            items={[
              { label: t('Papers'), href: '/papers' },
              {
                label: (
                  <Suspense fallback={<Bone.Text widths={['28ch']} />}>
                    <PaperCrumb id={id} />
                  </Suspense>
                ),
              },
            ]}
            t={t}
          />
        )
      )}

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <PaperRecordSkeleton
              t={t}
              features={features}
              back={runId ? t('Back to briefing') : undefined}
            />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <PaperRecord id={id} runId={runId} t={t} lang={lang} features={features} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

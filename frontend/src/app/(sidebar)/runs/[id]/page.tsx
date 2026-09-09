import { Breadcrumbs } from '@/components/scanner-ui'
import { isUuid } from '@/lib/bff/core/validate'
import { getLang, getT } from '@/lib/i18n-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { Suspense, ViewTransition } from 'react'
import { shortId } from '../run-presentation'
import { RunHead, Steps } from './sections'
import { RunHeadSkeleton, StepsSkeleton } from './skeletons'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  // Its own language read: generateMetadata runs independently of the page
  // body, so without it the tab would stay English on a German page.
  const t = await getT()
  return { title: t('Run') }
}

/**
 * The crumbs render with the shell (the id is in the URL); the head — header,
 * band, facts — and the steps stream in behind their own Suspense boundaries,
 * one fetch each. loading.tsx shows the same skeletons on navigation, and the
 * <ViewTransition> pairs animate the skeleton → content handoff.
 */
export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, t, lang] = await Promise.all([params, getT(), getLang()])
  if (!isUuid(id)) notFound()

  return (
    <div className="space-y-8">
      <Breadcrumbs t={t} items={[{ label: t('Runs'), href: '/runs' }, { label: shortId(id) }]} />

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <RunHeadSkeleton id={id} t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <RunHead id={id} t={t} lang={lang} />
        </ViewTransition>
      </Suspense>

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <StepsSkeleton t={t} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <Steps id={id} t={t} lang={lang} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

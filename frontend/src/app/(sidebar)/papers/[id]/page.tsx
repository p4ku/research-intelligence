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
import { PaperCrumb, PaperRecord } from './sections'
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
 * Detail is NOT behind `all_papers` — it is reached from briefings, Home and
 * chat citations — but everything on it that is derived from the list is: with
 * the flag off the whole crumb trail goes (a one-item trail whose only label
 * can be null renders an empty bar) and PaperNav loses its pager.
 */
export default async function PaperDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, t, lang, features] = await Promise.all([params, getT(), getLang(), getFeatures()])
  if (!isUuid(id)) notFound()

  return (
    <div className="mx-auto max-w-7xl">
      {features.all_papers && (
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
      )}

      <Suspense
        fallback={
          <ViewTransition exit="bone-exit" default="none">
            <PaperRecordSkeleton t={t} features={features} />
          </ViewTransition>
        }
      >
        <ViewTransition enter="bone-enter" default="none">
          <PaperRecord id={id} t={t} lang={lang} features={features} />
        </ViewTransition>
      </Suspense>
    </div>
  )
}

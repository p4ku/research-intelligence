import { AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { PageHeader, SectionLabel, StatBandSkeleton } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import { fmt, type T } from '@/lib/i18n'
import Link from 'next/link'
import { funnelCopy } from './data'
import { RunPapersSkeleton } from './run-papers'

/**
 * The dashboard's section skeletons — used both by loading.tsx (the whole-page
 * shell on navigation) and as the page's Suspense fallbacks, so the shell and
 * the streamed state are pixel-identical. One Skeleton.Region per section:
 * one status announcement, one scan sweep.
 */

export function FunnelSkeleton({ t }: { t: T }) {
  const copy = funnelCopy(t)
  return (
    <Skeleton.Region status={t('Loading the funnel')}>
      <StatBandSkeleton
        count={3}
        labels={copy.map((c) => c.label)}
        subs={copy.map((c) => c.sub)}
        flow
        className="lg:grid-cols-3!"
      />
    </Skeleton.Region>
  )
}

export function BriefSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading today’s brief')}>
      <AnswerMarkdownSkeleton
        className="mt-4 max-w-3xl text-base text-pretty text-zinc-600 dark:text-zinc-300"
        paragraphs={[3]}
      />
    </Skeleton.Region>
  )
}

export function PapersSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the papers')}>
      <RunPapersSkeleton />
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: real header and section labels, skeleton sections. */
export function DashboardSkeleton({ t, name }: { t: T; name: string }) {
  return (
    <div className="space-y-10">
      <PageHeader eyebrow={t('Today')} title={fmt(t('Good morning, {name}'), { name })} />

      <section className="scroll-mt-28">
        <FunnelSkeleton t={t} />
        <div className="mt-8">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <SectionLabel size="sm">{t('Today in brief')}</SectionLabel>
          </div>
          <BriefSkeleton t={t} />
        </div>
      </section>

      <section className="scroll-mt-28">
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
          <PapersSkeleton t={t} />
        </div>
      </section>
    </div>
  )
}

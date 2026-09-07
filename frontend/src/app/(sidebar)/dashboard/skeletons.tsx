import { CorpusSearch } from '@/components/corpus-search/corpus-search'
import { PageHeader, SectionLabel } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import type { Features } from '@/lib/features'
import { fmt, type T } from '@/lib/i18n'
import { RECENT } from './data'
import { HomeLinks } from './home-ui'
import { LedgerSkeleton } from './ledger'
import { RunCardSkeleton } from './run-card'

/**
 * Home's section skeleton — used both by loading.tsx (the whole-page shell
 * on navigation) and as the page's Suspense fallback, so the shell and the
 * streamed state are pixel-identical. One Skeleton.Region for the section:
 * one status announcement, one scan sweep.
 */

export function LedgerSkeletonRegion({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading recent briefings')}>
      <div className="grid gap-8 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <SectionLabel size="sm">{t('Recent briefings')}</SectionLabel>
            <HomeLinks t={t} />
          </div>
          <div className="mt-4">
            <LedgerSkeleton rows={RECENT} />
          </div>
        </div>
        <aside className="lg:col-span-1">
          <RunCardSkeleton />
        </aside>
      </div>
    </Skeleton.Region>
  )
}

/**
 * The loading.tsx shell: real header and search, skeleton section. The search
 * is the real component, not a bone, so it follows the page's `all_papers`
 * guard exactly — a shell that kept the field would paint a live search above
 * a corpus the reader cannot open. `features` is required because
 * dashboard/loading.tsx is the only caller.
 */
export function DashboardSkeleton({
  t,
  name,
  features,
}: {
  t: T
  name: string
  features: Features
}) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Home')} title={fmt(t('Good morning, {name}'), { name })} />
      {features.all_papers && <CorpusSearch domains={[]} />}
      <LedgerSkeletonRegion t={t} />
    </div>
  )
}

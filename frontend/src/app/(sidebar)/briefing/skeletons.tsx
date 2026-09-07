import { PageHeader } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { BriefingLedgerSkeleton } from './briefing-ledger'

/**
 * The archive's skeleton: the page's Suspense fallback (which knows the
 * domain names) and the loading.tsx body (which does not).
 */
export function LedgerSkeletonRegion({ t, domains }: { t: T; domains: string[] | null }) {
  return (
    <Skeleton.Region status={t('Loading the briefings')}>
      <BriefingLedgerSkeleton domains={domains} />
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the real header over the ledger's bones. */
export function BriefingPageSkeleton({ t }: { t: T }) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Briefings archive')} title={t('Briefings')} />
      <LedgerSkeletonRegion t={t} domains={null} />
    </div>
  )
}

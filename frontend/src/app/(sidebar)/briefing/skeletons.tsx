import { PageHeader } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import type { Features } from '@/lib/features'
import type { T } from '@/lib/i18n'
import { BriefingLedgerSkeleton } from './briefing-ledger'

/**
 * The archive's skeleton: the page's Suspense fallback (which knows the
 * domain names) and the loading.tsx body (which does not).
 *
 * Both take the flags as a required prop — nothing outside this route renders
 * them — so the bones lose the star column exactly when the ledger does.
 */
export function LedgerSkeletonRegion({
  t,
  domains,
  features,
}: {
  t: T
  domains: string[] | null
  features: Features
}) {
  return (
    <Skeleton.Region status={t('Loading the briefings')}>
      <BriefingLedgerSkeleton domains={domains} features={features} />
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the real header over the ledger's bones. */
export function BriefingPageSkeleton({ t, features }: { t: T; features: Features }) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Briefings archive')} title={t('Briefings')} />
      <LedgerSkeletonRegion t={t} domains={null} features={features} />
    </div>
  )
}

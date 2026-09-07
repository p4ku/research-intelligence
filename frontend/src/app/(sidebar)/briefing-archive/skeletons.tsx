import { PageHeader } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import type { Features } from '@/lib/features'
import type { T } from '@/lib/i18n'
import { EditionBrowserSkeleton } from './edition-browser'

/**
 * The archive's skeleton: the page's Suspense fallback and the loading.tsx
 * body. Both take the flags as a required prop — nothing outside this route
 * renders them — so the reader's star bone and the rail's Starred chip bone
 * go exactly when the controls do.
 */
export function EditionsSkeleton({ t, features }: { t: T; features: Features }) {
  return (
    <Skeleton.Region status={t('Loading the briefings')}>
      <EditionBrowserSkeleton features={features} />
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the real header over the reading-room skeleton. */
export function BriefingPageSkeleton({ t, features }: { t: T; features: Features }) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Daily briefings')} title={t('Briefings')} />
      <EditionsSkeleton t={t} features={features} />
    </div>
  )
}

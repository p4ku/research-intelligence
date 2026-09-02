import { PageHeader } from '@/components/scanner-ui'
import { Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { EditionBrowserSkeleton } from './edition-browser'

/** The archive's skeleton: the page's Suspense fallback and the loading.tsx body. */
export function EditionsSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the briefings')}>
      <EditionBrowserSkeleton />
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the real header over the reading-room skeleton. */
export function BriefingPageSkeleton({ t }: { t: T }) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Daily briefings')} title={t('Briefings')} />
      <EditionsSkeleton t={t} />
    </div>
  )
}

import { PaperCardSkeleton } from '@/components/paper-card'
import { PageHeader, SectionLabel } from '@/components/scanner-ui'
import { SearchFrame } from '@/components/search-frame'
import { Bone, Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'

/** One page of the browser's results — the browser and its skeleton share it. */
export const PER_PAGE = 8

/** The browser's filter groups, as label + a few option lines. */
const FILTER_GROUPS = ['Sort by', 'Screening', 'Ingested'] as const

/**
 * The papers browser's skeleton — used both by loading.tsx (the whole-page
 * shell on navigation) and as the page's Suspense fallback, so the shell and
 * the streamed state are pixel-identical: the search frame, the results
 * column of page-sized cards, and the filter rail beside them.
 */
export function PapersSkeletonRegion({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading papers')}>
      <div className="space-y-6">
        <SearchFrame>
          <Bone.Text widths={['34ch']} className="text-base" />
        </SearchFrame>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="mb-3 flex items-baseline gap-x-4 text-sm">
              <Bone.Text widths={['9ch']} />
            </div>
            <div className="space-y-3">
              {Array.from({ length: PER_PAGE }, (_, i) => (
                <PaperCardSkeleton key={i} />
              ))}
            </div>
          </div>
          <aside className="divide-y divide-line max-lg:order-first lg:col-span-1">
            {FILTER_GROUPS.map((label) => (
              <div key={label} className="py-5 first:pt-0 last:pb-0">
                <div className="flex items-center justify-between gap-3">
                  <SectionLabel className="shrink-0">{t(label)}</SectionLabel>
                  <Bone.Text widths={['10ch']} className="text-xs" />
                </div>
                <div className="mt-2 space-y-1">
                  {Array.from({ length: 3 }, (_, i) => (
                    <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 text-sm">
                      <Bone.Dot />
                      <Bone.Text widths={['12ch', '9ch', '14ch']} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </aside>
        </div>
      </div>
    </Skeleton.Region>
  )
}

/**
 * The loading.tsx shell: the title, an eyebrow bone where the page will
 * name the domain (or "All domains") once the workspaces are known, and the
 * skeleton browser.
 */
export function PapersSkeleton({ t }: { t: T }) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={<Bone.Text widths={['11ch']} />} title={t('Papers')} />
      <PapersSkeletonRegion t={t} />
    </div>
  )
}

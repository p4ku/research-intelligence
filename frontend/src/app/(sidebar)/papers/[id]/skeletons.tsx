import { Breadcrumbs } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import type { Features } from '@/lib/features'
import type { T } from '@/lib/i18n'
import { AssessmentSkeleton } from './assessment'
import { PaperChatSkeleton } from './paper-chat'
import { PaperCommentsSkeleton } from './paper-comments'
import { PaperHeaderSkeleton } from './paper-header'
import { PaperNavSkeleton } from './paper-nav'
import { ScoreRailSkeleton } from './score-rail'
import { RECORD_COLUMN, RECORD_GRID } from './sections'

/**
 * The paper page's skeleton — the page's Suspense fallback and, with the
 * crumbs, the loading.tsx shell, so both are pixel-identical. One record,
 * one Region, one sweep.
 *
 * It reserves the live domain's shape: the masthead with its metadata card
 * (the abstract collapsed inside it), seven definitions (ASSESSMENT_SHAPE)
 * and seven bars with a radar in the rail. A domain with fewer definitions
 * sees both shorten on load; a paper with a summary gains that section on
 * load — the skeleton cannot know.
 *
 * Both take the flags as a required prop — nothing outside this route renders
 * them, so a required prop catches a missed call site — and must mirror the
 * page exactly: with `all_papers` off there is no crumb trail and no pager,
 * or the shell paints chrome that then vanishes. The page's own fallback
 * also knows whether the URL names a briefing (`?run=`) and passes the back
 * label so the nav row does not reflow on load; loading.tsx sees no URL and
 * keeps the default.
 */

export function PaperRecordSkeleton({
  t,
  features,
  back,
}: {
  t: T
  features: Features
  /** The loaded row's back label when the paper was opened from a briefing. */
  back?: string
}) {
  return (
    <Skeleton.Region status={t('Loading the paper')}>
      <div className="mt-6">
        <PaperNavSkeleton t={t} features={features} back={back} />

        <div className={RECORD_GRID}>
          <div className={RECORD_COLUMN}>
            <PaperHeaderSkeleton features={features} />

            <AssessmentSkeleton />

            <footer className="border-t border-line pt-4 text-xs">
              <Bone.Text widths={['44ch']} />
            </footer>
          </div>

          <div className="lg:sticky lg:top-8">
            <ScoreRailSkeleton t={t} />
            <PaperChatSkeleton title={t('Ask this paper')} />
            <PaperCommentsSkeleton label={t('Comments')} />
          </div>
        </div>
      </div>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the crumb is a bone because loading.tsx gets no params. */
export function PaperPageSkeleton({ t, features }: { t: T; features: Features }) {
  return (
    <div className="mx-auto max-w-7xl">
      {features.all_papers && (
        <Breadcrumbs
          items={[
            { label: t('Papers'), href: '/papers' },
            { label: <Bone.Text widths={['28ch']} /> },
          ]}
          t={t}
        />
      )}
      <PaperRecordSkeleton t={t} features={features} />
    </div>
  )
}

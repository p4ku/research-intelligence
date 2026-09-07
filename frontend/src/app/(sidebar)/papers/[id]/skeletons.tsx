import { AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { Breadcrumbs, SectionLabel } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { AssessmentRowsSkeleton } from './assessment-rows'
import { PaperChatSkeleton } from './paper-chat'
import { PaperHeaderSkeleton } from './paper-header'
import { PaperNavSkeleton } from './paper-nav'
import { ScoreRailSkeleton } from './score-rail'

/**
 * The paper page's skeleton — the page's Suspense fallback and, with the
 * crumbs, the loading.tsx shell, so both are pixel-identical. One record,
 * one Region, one sweep.
 *
 * It reserves production's shape: five assessment rows and five bars with a
 * radar in the rail. A domain with fewer numeric dimensions sees the rail
 * shorten on load.
 */

export const ASSESSMENT_ROWS = 5

export function PaperRecordSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the paper')}>
      <div className="mt-6">
        <PaperNavSkeleton t={t} />

        <div className="mt-6 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 space-y-9">
            <PaperHeaderSkeleton />

            <section>
              <SectionLabel>{t('Screening')}</SectionLabel>
              <AnswerMarkdownSkeleton
                className="mt-3 max-w-[76ch] text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300"
                paragraphs={[4]}
              />
            </section>

            <section>
              <SectionLabel className="mb-3">{t('Assessment')}</SectionLabel>
              <AssessmentRowsSkeleton rows={ASSESSMENT_ROWS} />
            </section>

            <section>
              <SectionLabel>{t('Abstract')}</SectionLabel>
              <p className="mt-3 max-w-[76ch] text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
                <Bone.Text
                  lines={7}
                  widths={['100%', '100%', '96%', '100%', '98%', '100%', '62%']}
                />
              </p>
            </section>

            <footer className="border-t border-line pt-4 text-xs">
              <Bone.Text widths={['44ch']} />
            </footer>
          </div>

          <ScoreRailSkeleton t={t} />
        </div>

        <PaperChatSkeleton label={t('Ask this paper')} title={t('Ask this paper')} />
      </div>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the crumb is a bone because loading.tsx gets no params. */
export function PaperPageSkeleton({ t }: { t: T }) {
  return (
    <div className="mx-auto max-w-7xl">
      <Breadcrumbs
        items={[
          { label: t('Papers'), href: '/papers' },
          { label: <Bone.Text widths={['28ch']} /> },
        ]}
        t={t}
      />
      <PaperRecordSkeleton t={t} />
    </div>
  )
}

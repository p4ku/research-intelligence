import { AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import {
  Breadcrumbs,
  Card,
  DimensionsFrame,
  ScoreRowSkeleton,
  SectionLabel,
} from '@/components/scanner-ui'
import { SignalLedgerSkeleton } from '@/components/signal-ledger'
import { Bone, Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { PaperChatSkeleton } from './paper-chat'
import { PaperHeaderSkeleton, SignalHeading } from './paper-header'

/**
 * The paper page's skeleton — the page's Suspense fallback and, with the
 * crumbs, the loading.tsx shell, so both are pixel-identical. One record,
 * one Region, one sweep.
 *
 * Three deliberate reservations, all sized to what production renders:
 *  - the signal card takes the ledger's shape, including the compact
 *    `ScoreVariables` line under it (a workspace on another formula sees the
 *    card shrink on load);
 *  - the Profile card is reserved, and the Dimensions card is 3/5 wide to
 *    match — a paper with fewer than three scored dimensions drops the
 *    Profile card and widens Dimensions to 5/5 on load;
 *  - the dimension rows take the fixture's shape — the first explains itself
 *    with a rationale and a quote, the rest are bare numbers.
 */

export const DIMENSION_ROWS: { rationaleLines?: number; evidence?: number }[] = [
  { rationaleLines: 2, evidence: 1 },
  {},
  {},
]

export function PaperRecordSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the paper')}>
      <div className="mt-8 grid items-start gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="min-w-0 space-y-8">
          <PaperHeaderSkeleton />

          <Card>
            <SignalLedgerSkeleton heading={<SignalHeading t={t} />} />
            {/* The ledger branch always renders ScoreVariables under it:
                any canonical-formula workspace records at least one
                non-input variable, so the summary line is not optional. */}
            <div className="border-line-soft mt-4 border-t pt-3 text-xs">
              <Bone.Text widths={['22ch']} />
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <div className="flex items-center justify-between">
                <SectionLabel>{t('Dimensions')}</SectionLabel>
                <Bone.Chip width={56} />
              </div>
              <p className="mt-1 text-xs text-zinc-400">
                {t(
                  'Scored by the workspace’s extraction definitions, with the model’s rationale where it gave one.',
                )}
              </p>
              <DimensionsFrame state="skeleton" className="mt-5">
                {DIMENSION_ROWS.map((row, i) => (
                  <ScoreRowSkeleton key={i} {...row} />
                ))}
              </DimensionsFrame>
            </Card>
            <Card className="flex flex-col lg:col-span-2">
              <SectionLabel>{t('Profile')}</SectionLabel>
              <div className="flex flex-1 items-center justify-center">
                <Bone.Block className="mt-2" style={{ width: 240, height: 240 }} />
              </div>
            </Card>
          </div>

          <Card>
            <div className="flex items-center justify-between">
              <SectionLabel>{t('Screening')}</SectionLabel>
              <Bone.Chip width={104} />
            </div>
            <AnswerMarkdownSkeleton
              className="mt-2 text-sm text-zinc-700 dark:text-zinc-300"
              paragraphs={[3]}
            />
          </Card>

          <Card>
            <SectionLabel>{t('Abstract')}</SectionLabel>
            <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              <Bone.Text lines={5} widths={['100%', '100%', '96%', '100%', '62%']} />
            </p>
          </Card>

          <Card>
            <SectionLabel>{t('Files')}</SectionLabel>
            {/* The usual record: a source link, the stored PDF, and the
                archive note under them. */}
            <div className="mt-3 space-y-2 text-sm">
              <Bone.Text widths={['12ch']} />
              <Bone.Text widths={['26ch']} />
              <Bone.Text widths={['44ch']} className="text-xs" />
            </div>
          </Card>
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

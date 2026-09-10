'use client'

import { useFeatures } from '@/lib/features-client'
import { formatDate } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { dimensionLabel } from '@/lib/papers/dimension-label'
import { paperHref } from '@/lib/papers/href'
import { formatMeasure, isFitDimension, trlDimension } from '@/lib/papers/select'
import type { ScoredPaper } from '@/lib/papers/types'
import clsx from 'clsx'
import Link from 'next/link'
import type { ReactNode } from 'react'
import { DomainBadge, ScreeningPill, SignalScore, TrlBadge } from './scanner-ui'
import { Bone } from './skeleton'
import { StarButton } from './star'

// The loaded card's chrome, exactly as before the Frame split. The hover
// affordances key off the `group` wrapper (not the link itself) so the star
// in the corner — a sibling of the link, never inside it — keeps the card
// raised while it is hovered.
const CARD =
  'flex items-start gap-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-950/10 dark:bg-zinc-900 dark:ring-white/10'
const CARD_HOVER =
  'transition group-hover:-translate-y-px group-hover:shadow-md group-hover:ring-zinc-950/15 dark:group-hover:ring-white/20'

/**
 * Layout contract shared by PaperCard and PaperCardSkeleton: one set of slot
 * classes, so the skeleton cannot drift from the loaded card. The
 * data-shape/data-row markers are measured by scripts/skeleton-drift.ts via
 * the /studio/skeletons gallery.
 */
function PaperCardFrame({
  href,
  corner,
  score,
  meta,
  title,
  abstract,
  footer,
}: {
  /** Present on the loaded card; the skeleton renders a plain div. */
  href?: string
  /** The star, positioned over the card's top-right corner (loaded only). */
  corner?: ReactNode
  score: ReactNode
  meta: ReactNode
  title: ReactNode
  abstract: ReactNode
  footer: ReactNode
}) {
  const body = (
    <>
      {score}
      <div className="min-w-0 flex-1">
        {/* pr-8 keeps the meta row clear of the corner star. */}
        <div data-row="meta" className="flex flex-wrap items-center gap-2 pr-8">
          {meta}
        </div>
        <h3
          data-row="title"
          className="mt-1 text-base font-semibold text-pretty text-zinc-950 dark:text-white"
        >
          {title}
        </h3>
        {/* line-clamp only on the loaded card: clamping block bones renders
            unpredictably, and the skeleton's two fixed lines match the clamp. */}
        <p
          data-row="abstract"
          className={clsx('mt-1 text-sm text-zinc-500 dark:text-zinc-400', href && 'line-clamp-2')}
        >
          {abstract}
        </p>
        <div
          data-row="footer"
          className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs"
        >
          {footer}
        </div>
      </div>
    </>
  )
  return href ? (
    <div className="group relative">
      <Link
        href={href}
        data-shape="paper-card"
        data-state="loaded"
        className={clsx(CARD, CARD_HOVER)}
      >
        {body}
      </Link>
      {corner}
    </div>
  ) : (
    <div data-shape="paper-card" data-state="skeleton" className={CARD}>
      {body}
    </div>
  )
}

/**
 * `domain` names the paper's domain in the meta row — for lists that span
 * several. `href` replaces the plain permalink: a briefing's card carries its
 * run, so the page opens on the reading the card shows (see lib/papers/href).
 */
export function PaperCard({
  paper,
  domain,
  href,
}: {
  paper: ScoredPaper
  domain?: string
  href?: string
}) {
  const t = useT()
  const { lang } = useLanguage()
  const { stars } = useFeatures()
  const trl = trlDimension(paper)
  // The strip reads Schwarz Fit, then the next headline dimension in the
  // workspace's definition order, then the TRL chip: the fit is the number a
  // reader scans the list for, so it leads wherever the admin ranked its
  // definition, and the chip closes the strip rather than opening it.
  const stats = (paper.dimensions ?? [])
    .filter((d) => !d.is_trl && d.value !== null)
    .sort(
      (a, b) =>
        Number(isFitDimension(b)) - Number(isFitDimension(a)) || (a.order ?? 0) - (b.order ?? 0),
    )
    .slice(0, 2)
  const lead = paper.authors[0]
  return (
    <PaperCardFrame
      href={href ?? paperHref(paper.id)}
      corner={
        // Withheld, not rendered null: the flag hides the affordance, and the
        // slot is already optional and absolutely positioned, so nothing moves.
        stars ? (
          <StarButton kind="paper" id={paper.id} className="absolute top-2.5 right-2.5" />
        ) : undefined
      }
      score={<SignalScore score={paper.signal_score} lang={lang} />}
      meta={
        <>
          {domain && (
            <>
              <DomainBadge name={domain} tone="quiet" />
              <span className="text-xs text-zinc-400">·</span>
            </>
          )}
          <ScreeningPill status={paper.screening_status} t={t} />
          <span className="text-xs text-zinc-400">·</span>
          <span className="text-xs text-zinc-400">{paper.source}</span>
          <span className="text-xs text-zinc-400">·</span>
          <span className="text-xs text-zinc-400">{formatDate(paper.created_at, lang)}</span>
        </>
      }
      title={paper.title}
      abstract={paper.abstract}
      footer={
        <>
          {stats.map((d) => (
            <ScoreStat
              key={d.key}
              label={dimensionLabel(d.name, t)}
              value={formatMeasure(d.value, d.max, lang)}
            />
          ))}
          {trl?.value !== null && trl?.value !== undefined && <TrlBadge trl={trl.value} t={t} />}
          {paper.signal_score === null && <span className="text-zinc-400">{t('Unscored')}</span>}
          {lead && (
            <span className="ml-auto min-w-0 truncate text-zinc-400">
              {lead}
              {paper.authors.length > 1 && ` ${t('et al.')}`}
            </span>
          )}
        </>
      }
    />
  )
}

/**
 * The card's loading state: same frame, bones in the slots. The real `·`
 * separators stay so the meta row keeps its loaded rhythm. `scored={false}`
 * drops the TRL chip for lists where most rows are unscored.
 */
export function PaperCardSkeleton({ scored = true }: { scored?: boolean }) {
  return (
    <PaperCardFrame
      score={<Bone.Ring size={52} stroke={4} />}
      meta={
        <>
          <Bone.Chip width={104} />
          <span className="text-xs text-zinc-400">·</span>
          <Bone.Text widths={['5ch']} className="text-xs" />
          <span className="text-xs text-zinc-400">·</span>
          <Bone.Text widths={['11ch']} className="text-xs" />
        </>
      }
      title={<Bone.Text widths={['72%']} />}
      abstract={<Bone.Text lines={2} widths={['100%', '88%']} />}
      footer={
        <>
          <Bone.Text widths={['9ch']} className="text-xs" />
          <Bone.Text widths={['9ch']} className="text-xs" />
          {scored && <Bone.Chip width={124} />}
          <Bone.Text widths={['14ch']} className="ml-auto text-xs" />
        </>
      }
    />
  )
}

function ScoreStat({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-zinc-400">{label}</span>
      <span className="font-mono font-medium text-zinc-600 tabular-nums dark:text-zinc-300">
        {value}
      </span>
    </span>
  )
}

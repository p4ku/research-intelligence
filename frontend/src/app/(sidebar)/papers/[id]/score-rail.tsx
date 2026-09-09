import { RadarChart } from '@/components/charts'
import { Card, TrlBadge } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { formatNumber, type Lang, type T } from '@/lib/i18n'
import { dimensionLabel } from '@/lib/papers/dimension-label'
import { trlDimension } from '@/lib/papers/select'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'
import type { ReactNode } from 'react'
import { definitionAnchor } from './assessment'
import { ScoreBarFrame, ScoreBars, type RailBar } from './score-bars'

/**
 * The glance card beside the record: the Schwarz Score, the TRL chip,
 * one bar per definition — each a link to its article in the column, the
 * one being read marked — and the profile (the radar, values under its
 * labels) under a hairline. The rail column it sits in (sections.tsx) is
 * sticky on wide screens so the score mix stays in view while the
 * assessment is read; the card itself is not, so the ask composer under it
 * travels with it. Server-safe; the frame keeps the skeleton in step.
 */

// The rail's full inner width: the radar needs every pixel for its labels.
const RADAR = 260
const RADAR_H = Math.round(RADAR * 0.76)
const SCORE_CLASS =
  'font-mono text-[44px] leading-none font-medium tracking-tight text-zinc-950 tabular-nums dark:text-white'

export function ScoreRailFrame({
  state = 'loaded',
  label,
  score,
  chips,
  bars,
  radar,
}: {
  state?: 'loaded' | 'skeleton'
  label: string
  score: ReactNode
  chips: ReactNode
  bars: ReactNode
  /** Omitted when the paper has fewer than three numeric dimensions. */
  radar?: ReactNode
}) {
  return (
    <Card data-shape="score-rail" data-state={state}>
      <div data-row="score" className="flex items-baseline justify-between gap-4">
        <span className={SCORE_CLASS}>{score}</span>
        <span className="text-[11px] font-semibold tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
          {label}
        </span>
      </div>
      <div data-row="chips" className="mt-3 flex flex-wrap gap-1.5">
        {chips}
      </div>
      <ul className="mt-4 space-y-0.5">{bars}</ul>
      {radar && (
        <div data-row="radar" className="mt-4 flex justify-center border-t border-line-soft pt-4">
          {radar}
        </div>
      )}
    </Card>
  )
}

/**
 * "Sovereign Cloud & Commercial Viability" → "Sovereign Cloud"; a TRL
 * definition is just "TRL".
 *
 * The whole name is offered to the mapper first: a mapped dimension ("Fit
 * score", "Schwarz Fit") is product vocabulary and keeps the reading the
 * heading and the assessment give it, whatever punctuation it contains. Only
 * a name the mapper does not know — a domain's own wording — is shortened,
 * and then the shortened half goes through the mapper too, so a compound like
 * "Novelty (weighted)" still reads as the dimension.
 */
function shortName(d: Dimension, t: T): string {
  if (d.is_trl) return 'TRL'
  const mapped = dimensionLabel(d.name, t)
  if (mapped !== d.name) return mapped
  return dimensionLabel(d.name.split(/ \(| & /)[0]!, t)
}

/** Integers plain, otherwise at most two decimals — the reading the assessment uses too. */
function shownNumber(value: number | null, lang: Lang): string {
  return value === null ? '—' : formatNumber(value, lang, undefined, 2)
}

/** The radar's axes: the scaled dimensions, each printing the figure its bar shows, not a percentage. */
function radarAxes(dimensions: Dimension[], t: T, lang: Lang) {
  return dimensions
    .filter((d) => d.value !== null && d.max !== null && d.max > 0)
    .map((d) => ({
      label: shortName(d, t),
      value: Math.max(0, Math.min(100, (d.value! / d.max!) * 100)),
      shown: shownNumber(d.value, lang),
    }))
}

function railBar(d: Dimension, t: T, lang: Lang): RailBar {
  const hasBar = d.value !== null && d.max !== null && d.max > 0
  const shown =
    d.value !== null ? shownNumber(d.value, lang) : d.raw && d.raw !== '—' ? d.raw : null
  return {
    key: d.key + (d.extraction_id ?? ''),
    label: shortName(d, t),
    anchor: definitionAnchor(d),
    pct: hasBar ? Math.max(0, Math.min(1, d.value! / d.max!)) : null,
    value: (
      <>
        {shown}
        {hasBar && d.max !== 100 && (
          <span className="text-[10px] font-normal text-zinc-400">/{d.max}</span>
        )}
      </>
    ),
  }
}

export function ScoreRail({ paper, t, lang = 'en' }: { paper: ScoredPaper; t: T; lang?: Lang }) {
  // Exclude Risk & Affiliation dimensions from the score rail bars
  const visibleDimensions = (paper.dimensions ?? [])
    .filter((d) => !d.is_risk_and_affiliation && d.key !== 'risk_and_affiliation')
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  const trl = trlDimension(paper)
  const axes = radarAxes(visibleDimensions, t, lang)
  const score =
    paper.signal_score === null
      ? '—'
      : Number.isInteger(paper.signal_score)
        ? formatNumber(paper.signal_score, lang)
        : formatNumber(paper.signal_score, lang, 1)
  return (
    <ScoreRailFrame
      label={t('Schwarz Score')}
      score={score}
      chips={
        trl?.value !== null && trl?.value !== undefined ? (
          <TrlBadge trl={trl.value} t={t} />
        ) : undefined
      }
      bars={<ScoreBars bars={visibleDimensions.map((d) => railBar(d, t, lang))} />}
      radar={
        axes.length >= 3 && (
          <RadarChart axes={axes} color="var(--accent)" size={RADAR} valueLabels />
        )
      }
    />
  )
}

/**
 * The rail's bones. Seven bars and the radar — the live domain's shape; a
 * domain with fewer numeric dimensions sees the card shorten on load.
 */
export function ScoreRailSkeleton({ t, bars = 7 }: { t: T; bars?: number }) {
  return (
    <ScoreRailFrame
      state="skeleton"
      label={t('Schwarz Score')}
      score={<Bone.Number digits={4} />}
      chips={<Bone.Chip width={128} />}
      bars={Array.from({ length: bars }, (_, i) => (
        <ScoreBarFrame
          key={i}
          label={<Bone.Text widths={['7ch', '9ch', '8ch', '3ch', '6ch'].slice(i % 5)} />}
          value={<Bone.Number digits={2} />}
        />
      ))}
      radar={<Bone.Block style={{ width: RADAR, height: RADAR_H }} />}
    />
  )
}

import { RadarChart } from '@/components/charts'
import { Card, ScreeningPill, TrlBadge, dimensionRadarAxes } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { trlDimension } from '@/lib/papers/select'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'
import type { ReactNode } from 'react'

/**
 * The glance card beside the record: the Schwarz Score, the screening and
 * TRL chips, one bar per dimension, and the profile (the radar) under a
 * hairline. Sticky on wide screens so the score mix stays in view while the
 * assessment is read. Server-safe; the frame keeps the skeleton in step.
 */

const RADAR = 200
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
    <Card data-shape="score-rail" data-state={state} className="lg:sticky lg:top-8">
      <div data-row="score" className="flex items-baseline justify-between gap-4">
        <span className={SCORE_CLASS}>{score}</span>
        <span className="text-[11px] font-semibold tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
          {label}
        </span>
      </div>
      <div data-row="chips" className="mt-3 flex flex-wrap gap-1.5">
        {chips}
      </div>
      <ul className="mt-5 space-y-2.5">{bars}</ul>
      {radar && (
        <div data-row="radar" className="mt-5 flex justify-center border-t border-line-soft pt-4">
          {radar}
        </div>
      )}
    </Card>
  )
}

export function ScoreBarFrame({
  label,
  fill,
  value,
}: {
  label: ReactNode
  /** The track's fill; the skeleton leaves the track empty. */
  fill?: ReactNode
  value: ReactNode
}) {
  return (
    <li
      data-row="bar"
      className="grid grid-cols-[88px_minmax(0,1fr)_36px] items-center gap-2.5 text-xs text-zinc-600 dark:text-zinc-300"
    >
      <span className="truncate">{label}</span>
      <span className="block h-1 w-full overflow-hidden bg-line-soft">{fill}</span>
      <span className="text-right font-mono font-medium text-zinc-950 tabular-nums dark:text-white">
        {value}
      </span>
    </li>
  )
}

function shortName(d: Dimension): string {
  return d.is_trl ? 'TRL' : d.name
}

function ScoreBar({ dimension: d }: { dimension: Dimension }) {
  const hasBar = d.value !== null && d.max !== null && d.max > 0
  const pct = hasBar ? Math.max(0, Math.min(1, d.value! / d.max!)) : 0
  const shown =
    d.value === null
      ? '—'
      : Number.isInteger(d.value)
        ? String(d.value)
        : (Math.round(d.value * 100) / 100).toString()
  return (
    <ScoreBarFrame
      label={shortName(d)}
      fill={
        hasBar && (
          // scaleX rather than width so the glide runs off the main thread
          <span
            className="block h-full w-full origin-left bg-accent transition-transform duration-[250ms] ease-out"
            style={{ transform: `scaleX(${pct})` }}
          />
        )
      }
      value={
        <>
          {shown}
          {hasBar && d.max !== 100 && (
            <span className="text-[10px] font-normal text-zinc-400">/{d.max}</span>
          )}
        </>
      }
    />
  )
}

export function ScoreRail({ paper, t }: { paper: ScoredPaper; t: T }) {
  const trl = trlDimension(paper)
  const axes = dimensionRadarAxes(paper.dimensions)
  const score =
    paper.signal_score === null
      ? '—'
      : Number.isInteger(paper.signal_score)
        ? String(paper.signal_score)
        : paper.signal_score.toFixed(1)
  return (
    <ScoreRailFrame
      label={t('Schwarz Score')}
      score={score}
      chips={
        <>
          <ScreeningPill status={paper.screening_status} t={t} />
          {trl?.value !== null && trl?.value !== undefined && <TrlBadge trl={trl.value} t={t} />}
        </>
      }
      bars={paper.dimensions.map((d) => (
        <ScoreBar key={d.key + (d.extraction_id ?? '')} dimension={d} />
      ))}
      radar={
        axes.length >= 3 && (
          <RadarChart
            axes={axes.map((a, i) => ({ ...a, label: shortName(paper.dimensions[i]!) }))}
            color="var(--accent)"
            size={RADAR}
          />
        )
      }
    />
  )
}

/**
 * The rail's bones. Five bars and the radar — production's shape; a domain
 * with fewer numeric dimensions sees the card shorten on load.
 */
export function ScoreRailSkeleton({ t, bars = 5 }: { t: T; bars?: number }) {
  return (
    <ScoreRailFrame
      state="skeleton"
      label={t('Schwarz Score')}
      score={<Bone.Number digits={4} />}
      chips={
        <>
          <Bone.Chip width={104} />
          <Bone.Chip width={128} />
        </>
      }
      bars={Array.from({ length: bars }, (_, i) => (
        <ScoreBarFrame
          key={i}
          label={<Bone.Text widths={['7ch', '9ch', '8ch', '3ch', '6ch'].slice(i % 5)} />}
          value={<Bone.Number digits={2} />}
        />
      ))}
      radar={<Bone.Block style={{ width: RADAR, height: RADAR }} />}
    />
  )
}

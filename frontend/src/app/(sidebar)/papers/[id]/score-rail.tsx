import { RadarChart } from '@/components/charts'
import { Card, TrlBadge } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import { isResearchMetrics, trlDimension } from '@/lib/papers/select'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'
import type { ReactNode } from 'react'
import { definitionAnchor, subMeasureAnchor, subMeasuresOf } from './assessment'
import { ScoreBarFrame, ScoreBars, type RailBar } from './score-bars'

/**
 * The glance card beside the record: the Schwarz Score, the TRL chip,
 * one bar per definition — each a link to its article in the column, the
 * one being read marked — and the profile (the radar, values under its
 * labels) under a hairline. Research Metrics is the exception: its three
 * sub-scores (Rigour, Novelty, Significance) stand in for it, each a bar
 * and an axis of its own linking to its row, because the headline hides
 * how differently they can move. Sticky on wide screens so the score mix
 * stays in view while the assessment is read. Server-safe; the frame keeps
 * the skeleton in step.
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
      <ul className="mt-4 space-y-0.5">{bars}</ul>
      {radar && (
        <div data-row="radar" className="mt-4 flex justify-center border-t border-line-soft pt-4">
          {radar}
        </div>
      )}
    </Card>
  )
}

/** "Sovereign Cloud & Commercial Viability" → "Sovereign Cloud". */
function shortLabel(name: string): string {
  return name.split(/ \(| & /)[0]!
}

/** A definition's bar label; a TRL definition is just "TRL". */
function shortName(d: Dimension): string {
  return d.is_trl ? 'TRL' : shortLabel(d.name)
}

function shownNumber(value: number | null): string {
  return value === null
    ? '—'
    : Number.isInteger(value)
      ? String(value)
      : (Math.round(value * 100) / 100).toString()
}

/** One row of the rail — a definition, or one of Research Metrics' sub-scores. */
export interface RailEntry {
  key: string
  label: string
  /** The column id the bar links to: the definition's article, or the sub-score's row. */
  anchor: string
  value: number | null
  /** The scale the value is read against; null draws the figure without a track. */
  max: number | null
  /** See RailBar.watch: the first sub-score's row also answers for its article. */
  watch?: string[]
}

/**
 * The rail's rows, in definition order. Risk & Affiliation never appears
 * (it flags, it does not score). A Research Metrics definition with at
 * least two numeric sub-scores is replaced by them; with fewer it stays
 * one row, so a domain whose definition has no sub-scores — or whose
 * sub-scores arrived as prose only — keeps the figure it had.
 */
export function railEntries(paper: ScoredPaper): RailEntry[] {
  const visible = (paper.dimensions ?? []).filter(
    (d) =>
      d.key !== 'risk_and_affiliation' &&
      !d.name.toLowerCase().includes('risk') &&
      !d.name.toLowerCase().includes('affiliation'),
  )
  return visible.flatMap((d): RailEntry[] => {
    const own: RailEntry = {
      key: d.key + (d.extraction_id ?? ''),
      label: shortName(d),
      anchor: definitionAnchor(d),
      value: d.value,
      max: d.max,
    }
    if (!isResearchMetrics(d)) return [own]
    const { subMeasures } = subMeasuresOf(d)
    const figure = (v: number | null | undefined) =>
      typeof v === 'number' && Number.isFinite(v) ? v : null
    if (subMeasures.filter((sub) => figure(sub.value) !== null).length < 2) return [own]
    return subMeasures.map((sub, i) => ({
      key: `${own.key}-${sub.key}`,
      label: shortLabel(sub.name),
      anchor: subMeasureAnchor(d, sub),
      value: figure(sub.value),
      max: typeof sub.max === 'number' ? sub.max : null,
      ...(i === 0 ? { watch: [own.anchor] } : {}),
    }))
  })
}

/** The radar's axes: the scaled entries, each printing the figure its bar shows, not a percentage. */
function radarAxes(entries: RailEntry[]) {
  return entries
    .filter((e) => e.value !== null && e.max !== null && e.max > 0)
    .map((e) => ({
      label: e.label,
      value: Math.max(0, Math.min(100, (e.value! / e.max!) * 100)),
      shown: shownNumber(e.value),
    }))
}

function railBar(e: RailEntry): RailBar {
  const hasBar = e.value !== null && e.max !== null && e.max > 0
  const shown = shownNumber(e.value)
  return {
    key: e.key,
    label: e.label,
    anchor: e.anchor,
    watch: e.watch,
    pct: hasBar ? Math.max(0, Math.min(1, e.value! / e.max!)) : null,
    value: (
      <>
        {shown}
        {hasBar && e.max !== 100 && (
          <span className="text-[10px] font-normal text-zinc-400">/{e.max}</span>
        )}
      </>
    ),
  }
}

export function ScoreRail({ paper, t }: { paper: ScoredPaper; t: T }) {
  const entries = railEntries(paper)
  const trl = trlDimension(paper)
  const axes = radarAxes(entries)
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
        trl?.value !== null && trl?.value !== undefined ? (
          <TrlBadge trl={trl.value} t={t} />
        ) : undefined
      }
      bars={<ScoreBars bars={entries.map(railBar)} />}
      radar={
        axes.length >= 3 && (
          <RadarChart axes={axes} color="var(--accent)" size={RADAR} valueLabels />
        )
      }
    />
  )
}

/**
 * The rail's bones. Five bars and the radar — the live domain's shape
 * (three Research Metrics sub-scores, Schwarz Fit, TRL); a domain with
 * fewer numeric rows sees the card shorten on load.
 */
export function ScoreRailSkeleton({ t, bars = 5 }: { t: T; bars?: number }) {
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

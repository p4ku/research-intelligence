'use client'

// The signal score as a ledger: what it is made of (fit × 0.6, novelty × 0.4,
// the TRL bonus) on one bar, and sliders that re-run the formula so a reader
// can see what would move the paper. Render only with inputs from
// `ledgerInputs()` — that is the proof the decomposition applies to this
// record. No code is ever shown; the formula stays backend-owned.
//
// LedgerFrame owns the layout; SignalLedger fills it with the live formula and
// SignalLedgerSkeleton with bones. The skeleton deliberately touches none of
// the motion hooks: a spring on the score would fight the scan sweep.

import { DeltaBadge } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { fmt as interpolate } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { BONUS_TRL, GATE_TRL, evaluate, round2, type Inputs } from '@/lib/papers/signal-formula'
import clsx from 'clsx'
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'

// The bar spans the highest reachable score (100 × 1.25) so the bonus has room.
const BAR_MAX = 125
const pct = (n: number) => `${(Math.max(0, n) / BAR_MAX) * 100}%`
const num = (n: number) => (Number.isInteger(n) ? String(n) : round2(n).toString())

const SCORE_CLASS =
  'text-foreground block font-mono text-[34px] leading-none font-medium tabular-nums'

/* ---------------------------------- Frame ---------------------------------- */

function LedgerFrame({
  state,
  heading,
  score,
  note,
  bar,
  parts,
  gate,
  sliders,
}: {
  state: 'loaded' | 'skeleton'
  heading: ReactNode
  /** The big number, in SCORE_CLASS. */
  score: ReactNode
  /** The fixed-height line under it: "as scored", or the delta and reset. */
  note: ReactNode
  bar: ReactNode
  /** Three legend rows. */
  parts: ReactNode
  /** The TRL gate warning — conditional, so not a measured row. */
  gate?: ReactNode
  sliders: ReactNode
}) {
  return (
    <div data-shape="signal-ledger" data-state={state}>
      <div data-row="score" className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">{heading}</div>
        <div className="text-right">
          {score}
          <div className="mt-1.5 flex h-5 items-center justify-end gap-2 text-xs">{note}</div>
        </div>
      </div>

      {bar}

      <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">{parts}</dl>
      {gate}

      <div className="mt-5 grid gap-x-6 gap-y-4 border-t border-line-soft pt-4 sm:grid-cols-3">
        {sliders}
      </div>
    </div>
  )
}

/** The bar's track. Loaded fills it with segments; the empty track is the resting state. */
function BarTrack({
  dim = false,
  label,
  children,
}: {
  dim?: boolean
  /** Accessible description of the segments; omitted for the skeleton. */
  label?: string
  children?: ReactNode
}) {
  return (
    <div
      data-row="bar"
      className={clsx(
        'relative mt-5 h-3 w-full bg-line-soft transition-opacity duration-150',
        dim && 'opacity-40',
      )}
      role={label ? 'img' : undefined}
      aria-label={label}
    >
      {children}
    </div>
  )
}

function Row({
  swatch,
  label,
  value,
  dim,
}: {
  swatch: string
  label: string
  value: ReactNode
  dim?: boolean
}) {
  return (
    <div
      data-row="part"
      className={clsx(
        'flex items-baseline justify-between gap-3 transition-opacity duration-150',
        dim && 'opacity-50',
      )}
    >
      <dt className="flex min-w-0 items-center gap-2 text-zinc-500 dark:text-zinc-400">
        <span aria-hidden="true" className={clsx('size-2 shrink-0', swatch)} />
        <span className="truncate">{label}</span>
      </dt>
      <dd className="shrink-0 font-mono text-foreground tabular-nums">{value}</dd>
    </div>
  )
}

function SliderFrame({
  label,
  value,
  control,
  marks,
}: {
  label: string
  value: ReactNode
  control: ReactNode
  marks?: ReactNode
}) {
  return (
    <label data-row="slider" className="block">
      <span className="flex items-baseline justify-between text-xs">
        <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
        <span className="font-mono font-medium text-foreground tabular-nums">{value}</span>
      </span>
      {control}
      <span
        aria-hidden="true"
        className="relative mt-1 block h-3.5 font-mono text-[10px] text-zinc-400"
      >
        {marks}
      </span>
    </label>
  )
}

/* --------------------------------- Loaded ---------------------------------- */

export function SignalLedger({
  inputs: actualInputs,
  heading,
}: {
  inputs: Inputs
  /** Section label and description, rendered top-left of the score. */
  heading: ReactNode
}) {
  const t = useT()
  const reduce = useReducedMotion()
  const [w, setW] = useState<Inputs>(actualInputs)
  const e = evaluate(w)
  const actual = evaluate(actualInputs)
  const changed =
    w.trl !== actualInputs.trl || w.fit !== actualInputs.fit || w.novelty !== actualInputs.novelty
  const delta = round2(e.score - actual.score)

  const mv = useMotionValue(e.score)
  const spring = useSpring(mv, { stiffness: 260, damping: 30 })
  const text = useTransform(reduce ? mv : spring, (v) => (Math.round(v * 10) / 10).toFixed(1))
  useEffect(() => {
    mv.set(e.score)
  }, [e.score, mv])

  const seg = 'absolute inset-y-0 transition-[left,width] duration-[250ms] ease-[var(--ease-out)]'
  const labels = { trl: t('TRL level'), fit: t('Fit score'), novelty: t('Novelty score') }

  return (
    <LedgerFrame
      state="loaded"
      heading={heading}
      score={
        <motion.span className={SCORE_CLASS} aria-live="polite">
          {text}
        </motion.span>
      }
      note={
        changed ? (
          <>
            <DeltaBadge delta={delta} />
            <button
              type="button"
              onClick={() => setW(actualInputs)}
              className="text-zinc-500 underline-offset-2 hover:text-foreground hover:underline"
            >
              {interpolate(t('Reset to actual {n}'), { n: num(actual.score) })}
            </button>
          </>
        ) : (
          <span className="text-zinc-400">{t('as scored')}</span>
        )
      }
      bar={
        <BarTrack
          dim={!e.gate}
          label={`${labels.fit} ${num(e.fitPart)}, ${labels.novelty} ${num(e.noveltyPart)}, bonus ${num(e.bonus)}`}
        >
          <span className={clsx(seg, 'bg-accent')} style={{ left: 0, width: pct(e.fitPart) }} />
          <span
            className={clsx(seg, 'bg-accent/45')}
            style={{ left: pct(e.fitPart), width: pct(e.noveltyPart) }}
          />
          <span
            className={clsx(seg, 'bg-warn')}
            style={{ left: pct(e.base), width: pct(e.bonus) }}
          />
          <span
            aria-hidden="true"
            className="absolute -top-1 -bottom-1 w-px bg-line-strong"
            style={{ left: pct(100) }}
          />
          <span
            aria-hidden="true"
            className="absolute -top-4 -translate-x-1/2 font-mono text-[10px] text-zinc-400"
            style={{ left: pct(100) }}
          >
            100
          </span>
        </BarTrack>
      }
      parts={
        <>
          <Row swatch="bg-accent" label={`${labels.fit} × 0.6`} value={num(e.fitPart)} />
          <Row swatch="bg-accent/45" label={`${labels.novelty} × 0.4`} value={num(e.noveltyPart)} />
          <Row
            swatch="bg-warn"
            label={interpolate(t('TRL {n}+ bonus'), { n: BONUS_TRL })}
            value={e.bonus > 0 ? `+${num(e.bonus)}` : '—'}
            dim={e.bonus === 0}
          />
        </>
      }
      gate={
        !e.gate && (
          <p className="mt-2 inline-flex rounded-sm bg-red-500/10 px-2 py-0.5 text-xs text-red-700 dark:text-red-300">
            {interpolate(t('Below TRL {n} the score is 0, whatever the fit and novelty.'), {
              n: GATE_TRL,
            })}
          </p>
        )
      }
      sliders={
        <>
          <Slider
            label={labels.trl}
            value={w.trl}
            actual={actualInputs.trl}
            max={9}
            onChange={(v) => setW({ ...w, trl: v })}
            marks={[
              { at: GATE_TRL, label: t('gate') },
              { at: BONUS_TRL, label: '×1.25' },
            ]}
            actualWord={t('actual')}
          />
          <Slider
            label={labels.fit}
            value={w.fit}
            actual={actualInputs.fit}
            max={100}
            onChange={(v) => setW({ ...w, fit: v })}
            actualWord={t('actual')}
          />
          <Slider
            label={labels.novelty}
            value={w.novelty}
            actual={actualInputs.novelty}
            max={100}
            onChange={(v) => setW({ ...w, novelty: v })}
            actualWord={t('actual')}
          />
        </>
      }
    />
  )
}

function Slider({
  label,
  value,
  actual,
  max,
  onChange,
  marks = [],
  actualWord,
}: {
  label: string
  value: number
  actual: number
  max: number
  onChange: (v: number) => void
  marks?: { at: number; label: string }[]
  actualWord: string
}) {
  const changed = value !== actual
  return (
    <SliderFrame
      label={label}
      value={
        <>
          {num(value)}
          {changed && (
            <span className="ml-1.5 font-normal text-zinc-400">
              {actualWord} {num(actual)}
            </span>
          )}
        </>
      }
      control={
        <input
          type="range"
          min={0}
          max={max}
          step={1}
          value={value}
          onChange={(ev) => onChange(Number(ev.target.value))}
          className="mt-1.5 block h-1 w-full cursor-pointer"
          style={{ accentColor: 'var(--accent)' }}
          aria-label={label}
        />
      }
      marks={marks.map((m) => (
        <span
          key={m.at}
          className="absolute -translate-x-1/2 whitespace-nowrap"
          style={{ left: `${(m.at / max) * 100}%` }}
        >
          <span className="mx-auto mb-0.5 block h-1 w-px bg-line-strong" />
          {m.label}
        </span>
      ))}
    />
  )
}

/* -------------------------------- Skeleton --------------------------------- */

/**
 * The ledger's bones: the real legend and slider labels (they are static
 * copy), a four-digit score, the empty track, empty sliders. No motion.
 */
export function SignalLedgerSkeleton({ heading }: { heading: ReactNode }) {
  const t = useT()
  const labels = { trl: t('TRL level'), fit: t('Fit score'), novelty: t('Novelty score') }
  const swatch = 'bg-foreground/8'
  return (
    <LedgerFrame
      state="skeleton"
      heading={heading}
      score={
        <span className={SCORE_CLASS}>
          <Bone.Number digits={4} />
        </span>
      }
      note={<Bone.Text widths={['9ch']} />}
      bar={<BarTrack />}
      parts={
        <>
          <Row swatch={swatch} label={`${labels.fit} × 0.6`} value={<Bone.Number digits={4} />} />
          <Row
            swatch={swatch}
            label={`${labels.novelty} × 0.4`}
            value={<Bone.Number digits={4} />}
          />
          <Row
            swatch={swatch}
            label={interpolate(t('TRL {n}+ bonus'), { n: BONUS_TRL })}
            value={<Bone.Number digits={2} />}
          />
        </>
      }
      sliders={[labels.trl, labels.fit, labels.novelty].map((label) => (
        <SliderFrame
          key={label}
          label={label}
          value={<Bone.Number digits={2} />}
          control={<Bone.Block className="mt-1.5 h-1 w-full" round />}
        />
      ))}
    />
  )
}

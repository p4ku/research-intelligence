'use client'

// The signal score as a ledger: what it is made of (fit × 0.6, novelty × 0.4,
// the TRL bonus) on one bar, and sliders that re-run the formula so a reader
// can see what would move the paper. Render only with inputs from
// `ledgerInputs()` — that is the proof the decomposition applies to this
// record. No code is ever shown; the formula stays backend-owned.

import { DeltaBadge } from '@/components/scanner-ui'
import { fmt as interpolate } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { BONUS_TRL, GATE_TRL, evaluate, round2, type Inputs } from '@/lib/papers/signal-formula'
import clsx from 'clsx'
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { useEffect, useState } from 'react'

// The bar spans the highest reachable score (100 × 1.25) so the bonus has room.
const BAR_MAX = 125
const pct = (n: number) => `${(Math.max(0, n) / BAR_MAX) * 100}%`
const num = (n: number) => (Number.isInteger(n) ? String(n) : round2(n).toString())

export function SignalLedger({
  inputs: actualInputs,
  heading,
}: {
  inputs: Inputs
  /** Section label and description, rendered top-left of the score. */
  heading: React.ReactNode
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
    <div>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">{heading}</div>
        <div className="text-right">
          <motion.span
            className="text-foreground block font-mono text-[34px] leading-none font-medium tabular-nums"
            aria-live="polite"
          >
            {text}
          </motion.span>
          <div className="mt-1.5 flex h-5 items-center justify-end gap-2 text-xs">
            {changed ? (
              <>
                <DeltaBadge delta={delta} />
                <button
                  type="button"
                  onClick={() => setW(actualInputs)}
                  className="hover:text-foreground text-zinc-500 underline-offset-2 hover:underline"
                >
                  {interpolate(t('Reset to actual {n}'), { n: num(actual.score) })}
                </button>
              </>
            ) : (
              <span className="text-zinc-400">{t('as scored')}</span>
            )}
          </div>
        </div>
      </div>

      <div
        className={clsx(
          'bg-line-soft relative mt-5 h-3 w-full transition-opacity duration-150',
          !e.gate && 'opacity-40',
        )}
        role="img"
        aria-label={`${labels.fit} ${num(e.fitPart)}, ${labels.novelty} ${num(e.noveltyPart)}, bonus ${num(e.bonus)}`}
      >
        <span className={clsx(seg, 'bg-accent')} style={{ left: 0, width: pct(e.fitPart) }} />
        <span
          className={clsx(seg, 'bg-accent/45')}
          style={{ left: pct(e.fitPart), width: pct(e.noveltyPart) }}
        />
        <span className={clsx(seg, 'bg-warn')} style={{ left: pct(e.base), width: pct(e.bonus) }} />
        <span
          aria-hidden="true"
          className="bg-line-strong absolute -top-1 -bottom-1 w-px"
          style={{ left: pct(100) }}
        />
        <span
          aria-hidden="true"
          className="absolute -top-4 -translate-x-1/2 font-mono text-[10px] text-zinc-400"
          style={{ left: pct(100) }}
        >
          100
        </span>
      </div>

      <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
        <Row swatch="bg-accent" label={`${labels.fit} × 0.6`} value={num(e.fitPart)} />
        <Row swatch="bg-accent/45" label={`${labels.novelty} × 0.4`} value={num(e.noveltyPart)} />
        <Row
          swatch="bg-warn"
          label={interpolate(t('TRL {n}+ bonus'), { n: BONUS_TRL })}
          value={e.bonus > 0 ? `+${num(e.bonus)}` : '—'}
          dim={e.bonus === 0}
        />
      </dl>
      {!e.gate && (
        <p className="mt-2 inline-flex rounded-sm bg-red-500/10 px-2 py-0.5 text-xs text-red-700 dark:text-red-300">
          {interpolate(t('Below TRL {n} the score is 0, whatever the fit and novelty.'), {
            n: GATE_TRL,
          })}
        </p>
      )}

      <div className="border-line-soft mt-5 grid gap-x-6 gap-y-4 border-t pt-4 sm:grid-cols-3">
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
      </div>
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
  value: string
  dim?: boolean
}) {
  return (
    <div
      className={clsx(
        'flex items-baseline justify-between gap-3 transition-opacity duration-150',
        dim && 'opacity-50',
      )}
    >
      <dt className="flex min-w-0 items-center gap-2 text-zinc-500 dark:text-zinc-400">
        <span aria-hidden="true" className={clsx('size-2 shrink-0', swatch)} />
        <span className="truncate">{label}</span>
      </dt>
      <dd className="text-foreground shrink-0 font-mono tabular-nums">{value}</dd>
    </div>
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
    <label className="block">
      <span className="flex items-baseline justify-between text-xs">
        <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
        <span className="text-foreground font-mono font-medium tabular-nums">
          {num(value)}
          {changed && (
            <span className="ml-1.5 font-normal text-zinc-400">
              {actualWord} {num(actual)}
            </span>
          )}
        </span>
      </span>
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
      <span
        aria-hidden="true"
        className="relative mt-1 block h-3.5 font-mono text-[10px] text-zinc-400"
      >
        {marks.map((m) => (
          <span
            key={m.at}
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `${(m.at / max) * 100}%` }}
          >
            <span className="bg-line-strong mx-auto mb-0.5 block h-1 w-px" />
            {m.label}
          </span>
        ))}
      </span>
    </label>
  )
}

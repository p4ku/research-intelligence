'use client'

// The dials the scoring weights will one day expose, shown at the values the
// workspace runs today and deliberately not adjustable: the weighting is
// managed centrally, so this reads as a settings surface, not a control panel.
// Visual language matches signal-ledger.tsx — same bar segments, same slider
// markup — so a reader moving between Tuning and a paper sees one system.

import { SectionLabel } from '@/components/scanner-ui'
import { fmt as interpolate } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { Influence } from '@/lib/papers/tuning-profile'
import clsx from 'clsx'

const pctOf = (share: number) => `${Math.round(share * 100)}%`

/** The base bar: fit and novelty, in the ledger's colours and proportions. */
export function InfluenceBar({ profile }: { profile: Influence[] }) {
  const t = useT()
  const shares = profile.filter((i) => i.kind === 'share')
  const gate = profile.find((i) => i.kind === 'gate')

  return (
    <div>
      <div
        className="bg-line-soft relative h-3 w-full"
        role="img"
        aria-label={shares.map((s) => `${t(s.label)} ${pctOf(s.share!)}`).join(', ')}
      >
        {shares.map((s, i) => (
          <span
            key={s.key}
            className={clsx('absolute inset-y-0', i === 0 ? 'bg-accent' : 'bg-accent/45')}
            style={{
              left: pctOf(shares.slice(0, i).reduce((a, b) => a + b.share!, 0)),
              width: pctOf(s.share!),
            }}
          />
        ))}
      </div>

      {/* The pairs read as one phrase, so they sit together rather than
          justified to the card's far edge. */}
      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-1.5 text-xs">
        {shares.map((s, i) => (
          <Row
            key={s.key}
            swatch={i === 0 ? 'bg-accent' : 'bg-accent/45'}
            label={t(s.label)}
            value={interpolate(t('{n} of the base'), { n: pctOf(s.share!) })}
          />
        ))}
      </dl>

      {gate && (
        <p className="border-line-soft mt-4 border-t pt-3 text-xs text-zinc-500 dark:text-zinc-400">
          <span aria-hidden="true" className="bg-warn mr-2 inline-block size-2 align-middle" />
          {interpolate(
            t(
              '{label} is a threshold, not a weight: below {gate} the score is 0, and at {bonusAt} or above the total is multiplied by {bonus}.',
            ),
            {
              label: t(gate.label),
              gate: gate.gate!,
              bonusAt: gate.bonusAt!,
              bonus: gate.bonus!,
            },
          )}
        </p>
      )}
    </div>
  )
}

/** The same controls, disabled, at the values in force. */
export function TuningPanel({ profile }: { profile: Influence[] }) {
  const t = useT()
  const shares = profile.filter((i) => i.kind === 'share')
  const gate = profile.find((i) => i.kind === 'gate')

  return (
    <div>
      <SectionLabel>{t('The dials')}</SectionLabel>
      <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
        {t('These weights are managed centrally and apply to every paper in the workspace.')}
      </p>

      <div className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-3">
        {shares.map((s) => (
          <Dial
            key={s.key}
            label={t(s.label)}
            display={pctOf(s.share!)}
            value={s.share! * 100}
            max={100}
          />
        ))}
        {gate && (
          <Dial
            label={t(gate.label)}
            display={interpolate(t('gate {n}'), { n: gate.gate! })}
            value={gate.gate!}
            max={9}
            marks={[
              { at: gate.gate!, label: t('gate') },
              { at: gate.bonusAt!, label: `×${gate.bonus}` },
            ]}
          />
        )}
      </div>
    </div>
  )
}

function Row({ swatch, label, value }: { swatch: string; label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="flex min-w-0 items-center gap-2 text-zinc-500 dark:text-zinc-400">
        <span aria-hidden="true" className={clsx('size-2 shrink-0', swatch)} />
        <span className="truncate">{label}</span>
      </dt>
      <dd className="text-foreground shrink-0 font-mono tabular-nums">{value}</dd>
    </div>
  )
}

function Dial({
  label,
  display,
  value,
  max,
  marks = [],
}: {
  label: string
  display: string
  value: number
  max: number
  marks?: { at: number; label: string }[]
}) {
  return (
    <label className="block">
      <span className="flex items-baseline justify-between text-xs">
        <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
        <span className="text-foreground font-mono font-medium tabular-nums">{display}</span>
      </span>
      <input
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        disabled
        readOnly
        onChange={() => {}}
        className="mt-1.5 block h-1 w-full disabled:pointer-events-none disabled:opacity-50"
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

'use client'

import { SCORE_STEP } from '@/lib/papers/score'
import { ChevronDownIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useState, type ReactNode } from 'react'
import { SectionLabel } from './scanner-ui'
import { Bone } from './skeleton'

/**
 * The filter rail's parts, shared by the Papers browser and a briefing's
 * paper list so the two rails read as one control: a collapsible group, a
 * one-of-many option, and the minimum-score slider.
 */

/**
 * A collapsible filter group: label on the left, the group's current selection
 * on the right, and a chevron toggle. Open by default. The right-hand value
 * lets the whole filter state read at a glance — even with a group collapsed.
 */
export function FilterGroup({
  label,
  value,
  children,
}: {
  label: string
  value?: string
  children: ReactNode
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="py-5 first:pt-0 last:pb-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="group flex w-full items-center justify-between gap-3"
      >
        <SectionLabel className="shrink-0">{label}</SectionLabel>
        <span className="flex min-w-0 items-center gap-2">
          {value && (
            <span className="truncate text-xs text-zinc-500 dark:text-zinc-400">{value}</span>
          )}
          <ChevronDownIcon
            className={clsx(
              'size-4 shrink-0 text-zinc-400 transition-transform group-hover:text-zinc-600 dark:group-hover:text-zinc-300',
              !open && '-rotate-90',
            )}
          />
        </span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

/**
 * The group's loading state: the label as text, the value a bone, and
 * either `rows` option bones or the control's own skeleton as children.
 */
export function FilterGroupSkeleton({
  label,
  rows = 0,
  children,
}: {
  label: string
  rows?: number
  children?: ReactNode
}) {
  return (
    <div className="py-5 first:pt-0 last:pb-0">
      <div className="flex w-full items-center justify-between gap-3">
        <SectionLabel className="shrink-0">{label}</SectionLabel>
        <span className="flex min-w-0 items-center gap-2">
          <span className="text-xs">
            <Bone.Text widths={['9ch']} />
          </span>
          <ChevronDownIcon className="size-4 shrink-0 text-zinc-400" />
        </span>
      </div>
      {rows > 0 && (
        <div className="mt-2 space-y-1">
          {Array.from({ length: rows }, (_, i) => (
            <OptionButtonSkeleton key={i} />
          ))}
        </div>
      )}
      {children && <div className="mt-2">{children}</div>}
    </div>
  )
}

export function OptionButton({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm',
        active
          ? 'bg-zinc-950/5 text-zinc-950 dark:bg-white/10 dark:text-white'
          : 'text-zinc-600 hover:bg-zinc-950/5 dark:text-zinc-300 dark:hover:bg-white/5',
      )}
    >
      <span
        aria-hidden="true"
        className={clsx('size-1.5 shrink-0', active ? 'bg-accent' : 'bg-transparent')}
      />
      {label}
    </button>
  )
}

function OptionButtonSkeleton() {
  return (
    <div className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm">
      <span aria-hidden="true" className="size-1.5 shrink-0 bg-transparent" />
      <Bone.Text widths={['11ch']} />
    </div>
  )
}

/**
 * The minimum-score slider: the floor's figure at the right of its label
 * (0 at rest — no "Any" doubling the group's header, per the stakeholder),
 * the range in steps, and the two ends named under it.
 */
export function MinScoreSlider({
  value,
  ceiling,
  step = SCORE_STEP,
  onChange,
  labels,
}: {
  value: number
  ceiling: number
  step?: number
  onChange: (value: number) => void
  labels: { minimum: string; low: string; high: string }
}) {
  return (
    <>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">{labels.minimum}</span>
        <span className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">{value}</span>
      </div>
      <input
        type="range"
        aria-label={labels.minimum}
        min={0}
        max={ceiling}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rs-slider"
        // A floor above the ceiling would paint the track past its end.
        style={
          {
            '--fill': `${Math.min(100, (value / ceiling) * 100)}%`,
          } as React.CSSProperties
        }
      />
      <div className="mt-1.5 flex justify-between text-xs text-zinc-400">
        <span>{labels.low}</span>
        <span>{labels.high}</span>
      </div>
    </>
  )
}

/** The slider's loading state: same rows, the track drawn empty. */
export function MinScoreSliderSkeleton({
  labels,
}: {
  labels: { minimum: string; low: string; high: string }
}) {
  return (
    <>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">{labels.minimum}</span>
        <span className="text-xs">
          <Bone.Text widths={['4ch']} />
        </span>
      </div>
      <div
        aria-hidden="true"
        className="rs-slider"
        style={{ '--fill': '0%' } as React.CSSProperties}
      />
      <div className="mt-1.5 flex justify-between text-xs text-zinc-400">
        <span>{labels.low}</span>
        <span>{labels.high}</span>
      </div>
    </>
  )
}

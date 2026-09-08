import { Bone } from '@/components/skeleton'
import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import {
  formatDuration,
  formatTokens,
  formatUsd,
  StepStatus,
  StepSummary,
  StepSummarySkeleton,
} from '../run-presentation'

// Small mono annotations: the component name on the title line, the model
// under the cost. Shared so the skeleton's bones inherit the same metrics.
const MONO_NOTE = 'font-mono text-[11px] text-zinc-400 dark:text-zinc-500'

interface StepRow {
  key: string
  /** Colour classes for the rail dot; the frame owns its geometry. */
  tone: string
  label: ReactNode
  status: ReactNode
  /** The rest of the title line: attempt chip, component name. */
  extras?: ReactNode
  summary: ReactNode
  /** Under the summary: error message, storage path. */
  below?: ReactNode
  bar: ReactNode
  duration: ReactNode
  cost: ReactNode
  model?: ReactNode
}

/**
 * Layout contract shared by StepTimeline and StepTimelineSkeleton: one set of
 * classes for the rail, the title line, the summary and the right rail, so the
 * skeleton cannot drift from the loaded list. data-shape/data-row are measured
 * by scripts/skeleton-drift.ts via the /studio/skeletons gallery.
 */
function StepTimelineFrame({ rows, state }: { rows: StepRow[]; state: 'loaded' | 'skeleton' }) {
  return (
    <ol data-shape="step-timeline" data-state={state} className="divide-y divide-line-soft">
      {rows.map((row, index) => {
        const isLast = index === rows.length - 1
        return (
          <li key={row.key} data-row="step" className="relative flex gap-4 py-4">
            {/* Rail: a dot per step, joined into a line except after the last. */}
            <div className="relative flex w-3 shrink-0 justify-center" aria-hidden="true">
              <span
                className={clsx(
                  'z-10 mt-1.5 size-2 shrink-0 rounded-full ring-4',
                  'ring-surface',
                  row.tone,
                )}
              />
              {!isLast && (
                <span className="absolute top-2 bottom-[-2.5rem] w-px bg-zinc-200 dark:bg-zinc-700" />
              )}
            </div>

            <div className="grid min-w-0 flex-1 gap-x-6 gap-y-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="text-sm font-medium text-zinc-950 dark:text-white">
                    {row.label}
                  </span>
                  {row.status}
                  {row.extras}
                </div>

                <div className="mt-1.5">{row.summary}</div>

                {row.below}
              </div>

              <div className="flex items-baseline gap-4 sm:w-56 sm:flex-col sm:items-end sm:gap-1">
                <div className="flex w-full items-center gap-2 sm:justify-end">
                  {row.bar}
                  <span className="text-sm text-zinc-700 tabular-nums dark:text-zinc-300">
                    {row.duration}
                  </span>
                </div>
                <div className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                  {row.cost}
                </div>
                {row.model}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** The rail dot's colour per status. `running` pulses: that is status, not a bone. */
function toneFor(status: ComponentRun['status']): string {
  switch (status) {
    case 'completed':
      return 'bg-emerald-500'
    case 'running':
      return 'animate-pulse bg-blue-500'
    case 'failed':
      return 'bg-red-500'
    default:
      return 'bg-zinc-300 dark:bg-zinc-600'
  }
}

/**
 * The run's steps in execution order, each with a duration bar drawn to the
 * same scale. The bar is the point: it answers "where did the time go" at a
 * glance, which a column of numbers does not.
 */
export function StepTimeline({ steps }: { steps: ComponentRun[] }) {
  const longest = steps.reduce((max, step) => Math.max(max, step.duration_seconds ?? 0), 0)

  // A rerun re-executes one step after the run has otherwise moved on, so the
  // same component legitimately appears twice, out of nominal stage order.
  // Numbering the repeats stops that reading as a duplicated row.
  const seen = new Map<string, number>()
  const attempts = steps.map((step) => {
    const n = (seen.get(step.component_name) ?? 0) + 1
    seen.set(step.component_name, n)
    return n
  })
  const total = new Map(seen)

  const rows = steps.map((step, index): StepRow => {
    const attempt = attempts[index]
    const repeated = (total.get(step.component_name) ?? 1) > 1
    const seconds = step.duration_seconds ?? 0
    // Percentages are relative to the slowest step, not the run total, so
    // short steps stay visible when one stage dominates.
    const width = longest > 0 ? Math.max((seconds / longest) * 100, seconds > 0 ? 2 : 0) : 0

    return {
      key: step.id,
      tone: toneFor(step.status),
      label: step.label,
      status: <StepStatus status={step.status} />,
      extras: (
        <>
          {repeated && (
            <span
              className="rounded-sm bg-zinc-100 px-1.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
              title="This step ran more than once in this pipeline run"
            >
              Attempt {attempt}
            </span>
          )}
          {/* Only worth showing when it isn't already the label. */}
          {step.label.toLowerCase() !== step.component_name.replace(/_/g, ' ') && (
            <code className={MONO_NOTE}>{step.component_name}</code>
          )}
        </>
      ),
      summary: <StepSummary summary={step.summary} />,
      below: (
        <>
          {step.error_message && (
            <p className="mt-2 rounded-sm bg-red-50 px-2 py-1.5 font-mono text-[11px] break-words whitespace-normal text-red-800 dark:bg-red-500/10 dark:text-red-300">
              {step.error_message}
            </p>
          )}
          {step.storage_path && (
            <p className={clsx('mt-1.5 truncate', MONO_NOTE)} title={step.storage_path}>
              {step.storage_path}
            </p>
          )}
        </>
      ),
      bar: (
        <div
          className="hidden h-1 w-24 overflow-hidden rounded-full bg-zinc-100 sm:block dark:bg-zinc-800"
          aria-hidden="true"
        >
          <div className="h-full rounded-full bg-accent" style={{ width: `${width}%` }} />
        </div>
      ),
      duration: formatDuration(step.duration_seconds),
      cost: (
        <>
          {formatUsd(step.cost.usd)}
          {step.cost.total_tokens !== null && (
            <span className="text-zinc-400 dark:text-zinc-500">
              {' · '}
              {formatTokens(step.cost.total_tokens)} tok
            </span>
          )}
        </>
      ),
      model: step.cost.model ? (
        <code className={clsx('max-w-full truncate', MONO_NOTE)} title={step.cost.model}>
          {step.cost.model}
        </code>
      ) : undefined,
    }
  })

  return <StepTimelineFrame rows={rows} state="loaded" />
}

// A typical run: fetch, download and OCR record no spend; the LLM steps that
// follow carry a cost line with tokens and a model line. Fixed patterns, never
// random — this is the same shape as the component-runs fixture the drift
// check measures against.
const LABEL_WIDTHS = ['12ch', '8ch', '10ch', '18ch', '20ch', '12ch']
const COUNTS = [3, 1, 1, 3, 3, 3]
const SPEND_FROM = 3

/** The timeline's loading state: `steps` bone rows in the same frame. */
export function StepTimelineSkeleton({ steps = 6 }: { steps?: number }) {
  const rows = Array.from({ length: steps }, (_, i): StepRow => {
    const spend = i >= SPEND_FROM
    return {
      key: `bone-${i}`,
      tone: 'bg-foreground/8',
      label: <Bone.Text widths={[LABEL_WIDTHS[i % LABEL_WIDTHS.length]]} />,
      status: <Bone.Chip width={72} />,
      extras: (
        <code className={MONO_NOTE}>
          <Bone.Text widths={['18ch']} />
        </code>
      ),
      summary: <StepSummarySkeleton counts={COUNTS[i % COUNTS.length]} />,
      bar: <Bone.Block round className="hidden h-1 w-24 sm:block" />,
      duration: <Bone.Text widths={['5ch']} />,
      cost: <Bone.Text widths={[spend ? '16ch' : '3ch']} />,
      model: spend ? (
        <code className={clsx('max-w-full truncate', MONO_NOTE)}>
          <Bone.Text widths={['22ch']} />
        </code>
      ) : undefined,
    }
  })
  return <StepTimelineFrame rows={rows} state="skeleton" />
}

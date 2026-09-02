import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import clsx from 'clsx'
import {
  formatDuration,
  formatTokens,
  formatUsd,
  StepStatus,
  StepSummary,
} from '../../run-presentation'

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

  return (
    <ol className="divide-line-soft divide-y">
      {steps.map((step, index) => {
        const attempt = attempts[index]
        const repeated = (total.get(step.component_name) ?? 1) > 1
        const seconds = step.duration_seconds ?? 0
        // Percentages are relative to the slowest step, not the run total, so
        // short steps stay visible when one stage dominates.
        const width = longest > 0 ? Math.max((seconds / longest) * 100, seconds > 0 ? 2 : 0) : 0
        const isLast = index === steps.length - 1

        return (
          <li key={step.id} className="relative flex gap-4 py-4">
            {/* Rail: a dot per step, joined into a line except after the last. */}
            <div className="relative flex w-3 shrink-0 justify-center" aria-hidden="true">
              <span
                className={clsx(
                  'z-10 mt-1.5 size-2 shrink-0 rounded-full ring-4',
                  'ring-surface',
                  step.status === 'completed' && 'bg-emerald-500',
                  step.status === 'running' && 'animate-pulse bg-blue-500',
                  step.status === 'failed' && 'bg-red-500',
                  (step.status === 'skipped' ||
                    step.status === 'pending' ||
                    step.status === 'aborted') &&
                    'bg-zinc-300 dark:bg-zinc-600',
                )}
              />
              {!isLast && (
                <span className="absolute top-2 bottom-[-1.25rem] w-px bg-zinc-200 dark:bg-zinc-700" />
              )}
            </div>

            <div className="grid min-w-0 flex-1 gap-x-6 gap-y-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="text-sm font-medium text-zinc-950 dark:text-white">
                    {step.label}
                  </span>
                  <StepStatus status={step.status} />
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
                    <code className="font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
                      {step.component_name}
                    </code>
                  )}
                </div>

                <div className="mt-1.5">
                  <StepSummary summary={step.summary} />
                </div>

                {step.error_message && (
                  <p className="mt-2 rounded-sm bg-red-50 px-2 py-1.5 font-mono text-[11px] break-words whitespace-normal text-red-800 dark:bg-red-500/10 dark:text-red-300">
                    {step.error_message}
                  </p>
                )}

                {step.storage_path && (
                  <p
                    className="mt-1.5 truncate font-mono text-[11px] text-zinc-400 dark:text-zinc-500"
                    title={step.storage_path}
                  >
                    {step.storage_path}
                  </p>
                )}
              </div>

              <div className="flex items-baseline gap-4 sm:w-56 sm:flex-col sm:items-end sm:gap-1">
                <div className="flex w-full items-center gap-2 sm:justify-end">
                  <div
                    className="hidden h-1 w-24 overflow-hidden rounded-full bg-zinc-100 sm:block dark:bg-zinc-800"
                    aria-hidden="true"
                  >
                    <div className="bg-accent h-full rounded-full" style={{ width: `${width}%` }} />
                  </div>
                  <span className="text-sm text-zinc-700 tabular-nums dark:text-zinc-300">
                    {formatDuration(step.duration_seconds)}
                  </span>
                </div>
                <div className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                  {formatUsd(step.cost.usd)}
                  {step.cost.total_tokens !== null && (
                    <span className="text-zinc-400 dark:text-zinc-500">
                      {' · '}
                      {formatTokens(step.cost.total_tokens)} tok
                    </span>
                  )}
                </div>
                {step.cost.model && (
                  <code
                    className="max-w-full truncate font-mono text-[11px] text-zinc-400 dark:text-zinc-500"
                    title={step.cost.model}
                  >
                    {step.cost.model}
                  </code>
                )}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

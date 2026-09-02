/**
 * The run's steps as a spine of stages: one row per stage the engine ran,
 * with the typed summary the BFF resolved, the duration and any error;
 * stages it never reached collapse into one row. Steps the strip does not
 * model (metrics, deep research, unknown) follow as their own rows. Evidence
 * only — nothing here is inferred from `current_stage`. Client-safe.
 */
import { Bone } from '@/components/skeleton'
import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import { stageLabel, STAGES, type PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'
import { formatDuration, StepSummary } from '../run-presentation'
import { fmtClockUtc, relativeAge, stageForStep } from './derive'
import type { Loadable } from './loadable'
import { MONO, Msg, STATUS_LABEL } from './primitives'

const MARK: Record<string, string> = {
  completed: 'bg-foreground/25',
  skipped: 'bg-foreground/25',
  running: 'bg-accent',
  failed: 'bg-negative',
  aborted: 'bg-negative',
  pending: 'bg-line-soft',
}

const ROW =
  'border-line-soft grid grid-cols-[9px_minmax(0,1fr)_auto] items-start gap-2.5 border-b py-2'

function StepRow({
  n,
  name,
  step,
  now,
}: {
  n: number | null
  name: string
  step: ComponentRun
  now: string
}) {
  const label =
    step.status === 'skipped'
      ? 'Skipped'
      : (STATUS_LABEL[step.status as keyof typeof STATUS_LABEL] ?? step.status)
  return (
    <li className={ROW} data-row="step">
      <span
        aria-hidden="true"
        className={clsx('mt-1 block size-[9px]', MARK[step.status] ?? 'bg-line-soft')}
      />
      <span className="min-w-0">
        <span className="block text-[12.5px] font-medium break-words">
          {n !== null && <>{n}. </>}
          {name} — {label}
        </span>
        <span className="text-muted-foreground mt-0.5 block text-xs">
          <StepSummary summary={step.summary} />
        </span>
        <span className="text-muted-foreground mt-0.5 block text-xs break-words">
          {step.component_name}
          {step.status === 'running' && step.started_at && (
            <>
              {' '}
              · started {fmtClockUtc(step.started_at)} UTC, {relativeAge(step.started_at, now)}
            </>
          )}
        </span>
        {step.error_message && (
          <Msg tone="neg" className="mt-1.5">
            {step.error_message}
          </Msg>
        )}
      </span>
      <span className={clsx(MONO, 'text-muted-foreground text-xs whitespace-nowrap')}>
        {step.status === 'running' ? 'running' : formatDuration(step.duration_seconds)}
      </span>
    </li>
  )
}

export function StepSpine({
  run,
  steps,
  now,
}: {
  run: PipelineRun
  steps: Loadable<ComponentRun[]>
  now: string
}) {
  if (steps.status === 'loading' || steps.status === 'idle') return <StepSpineSkeleton />
  if (steps.status === 'error') return <Msg tone="mut">{steps.message}</Msg>
  if (steps.data.length === 0) {
    return (
      <Msg tone="mut">
        No step records were kept for this run.
        {run.current_stage && (
          <>
            {' '}
            Its last stage dispatched was{' '}
            <b className="font-medium">{stageLabel(run.current_stage)}</b>.
          </>
        )}
      </Msg>
    )
  }
  const byStage = new Map<string, ComponentRun[]>()
  const extra: ComponentRun[] = []
  for (const step of steps.data) {
    const stage = stageForStep(step)
    if (!stage) {
      extra.push(step)
      continue
    }
    const list = byStage.get(stage) ?? []
    list.push(step)
    byStage.set(stage, list)
  }
  const missing: string[] = []
  const rows: React.ReactNode[] = []
  STAGES.forEach((stage, i) => {
    const list = byStage.get(stage)
    if (!list) {
      missing.push(`${i + 1}. ${stageLabel(stage)}`)
      return
    }
    for (const step of list) {
      rows.push(<StepRow key={step.id} n={i + 1} name={stageLabel(stage)} step={step} now={now} />)
    }
  })
  for (const step of extra) {
    rows.push(<StepRow key={step.id} n={null} name={step.label} step={step} now={now} />)
  }
  return (
    <ol className="border-line-soft border-t" data-shape="step-spine">
      {rows}
      {missing.length > 0 && (
        <li className={ROW} data-row="step">
          <span
            aria-hidden="true"
            className="ring-line-soft mt-1 block size-[9px] ring-1 ring-inset"
          />
          <span className="min-w-0">
            <span className="text-muted-foreground block text-[12.5px] break-words">
              {run.status === 'running' ? 'Not yet dispatched' : 'Not reached'}
            </span>
            <span className="text-muted-foreground mt-0.5 block text-xs break-words">
              {missing.join(' · ')}
            </span>
          </span>
          <span className={clsx(MONO, 'text-muted-foreground text-xs whitespace-nowrap')}>
            {missing.length} of {STAGES.length}
          </span>
        </li>
      )}
    </ol>
  )
}

/**
 * `rows` step rows: three lines each, except the last, which stands in for
 * the "Not reached" row every real run has (the engine never dispatches all
 * eight stages) and carries two.
 */
export function StepSpineSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <ol className="border-line-soft border-t" data-shape="step-spine" data-state="skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className={ROW} data-row="step">
          <Bone.Block className="mt-1 size-[9px]" />
          <span className="min-w-0">
            <span className="block text-[12.5px]">
              <Bone.Text widths={[i % 2 ? '22ch' : '18ch']} />
            </span>
            <span className="mt-0.5 block text-xs">
              <Bone.Text widths={[i === rows - 1 ? '32ch' : '16ch']} />
            </span>
            {i < rows - 1 && (
              <span className="mt-0.5 block text-xs">
                <Bone.Text widths={['12ch']} />
              </span>
            )}
          </span>
          <Bone.Number digits={5} className="text-xs" />
        </li>
      ))}
    </ol>
  )
}

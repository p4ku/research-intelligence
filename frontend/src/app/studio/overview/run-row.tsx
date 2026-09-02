'use client'

/**
 * One run in the list. A button, not a link: it expands the detail pane
 * (`aria-expanded` / `aria-controls`), and the pane carries the one real
 * permalink to /studio/runs/[id]. The row stays thin for calm runs and
 * grows a stage strip and the engine's message for anything that needs
 * eyes.
 */
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'
import { forwardRef } from 'react'
import { formatDuration, formatTokens, formatUsd, shortId } from '../run-presentation'
import {
  elapsed,
  fmtClockUtc,
  fmtDate,
  percentOf,
  relativeAge,
  runMarks,
  triggerText,
  type RunIndex,
} from './derive'
import { Chip, FOCUS, MONO, Msg, StatusChip } from './primitives'
import { StageSegments } from './stage-segments'

export const ROW_CLASS =
  'block w-full border-b border-line-soft px-3 py-2.5 text-left last:border-b-0'

export const RunRow = forwardRef<
  HTMLButtonElement,
  {
    run: PipelineRun
    index: RunIndex
    /** Whether the list spans workspaces (then the workspace names the row). */
    showWorkspace: boolean
    open: boolean
    now: string
    onOpen: (id: string) => void
  }
>(function RunRow({ run, index, showWorkspace, open, now, onOpen }, ref) {
  const title = showWorkspace ? run.workspace_name : (run.schedule_name ?? 'Manual run')
  const sub = showWorkspace
    ? triggerText(run)
    : run.schedule_name
      ? 'schedule'
      : run.triggered_by
        ? `by ${run.triggered_by}`
        : null
  const marks = runMarks(run, index)
  const calm = run.status === 'completed'
  const msgTone = run.status === 'running' ? 'acc' : run.status === 'pending' ? 'mut' : 'neg'

  return (
    <button
      ref={ref}
      type="button"
      data-row="run"
      data-run={run.id}
      aria-expanded={open}
      aria-controls="run-detail"
      onClick={() => onOpen(run.id)}
      className={clsx(
        ROW_CLASS,
        FOCUS,
        'hover:bg-foreground/3 transition-colors duration-150',
        open && 'bg-accent/6 hover:bg-accent/9 shadow-[inset_2px_0_0_var(--color-accent)]',
      )}
    >
      <span className="flex items-baseline gap-2.5">
        <span className={clsx(MONO, 'text-muted-foreground shrink-0 text-xs')}>
          {run.started_at ? fmtClockUtc(run.started_at) : '—'}
          <span className="sr-only"> UTC on {fmtDate(run.run_date)}</span>
        </span>
        <span className="min-w-0 flex-1 text-[13px] font-medium break-words">
          {title}
          <span className="text-muted-foreground mt-px block text-xs font-normal break-words">
            {sub && <>{sub} · </>}
            <span className={MONO}>{shortId(run.id)}</span>
          </span>
        </span>
        <span className="ml-auto shrink-0">
          <StatusChip status={run.status} />
        </span>
      </span>

      {marks.length > 0 && (
        <span className="mt-1.5 flex flex-wrap gap-1">
          <Chip tone="plain">{marks.join(' · ')}</Chip>
        </span>
      )}

      <span className="text-muted-foreground mt-1.5 flex flex-wrap gap-x-3.5 gap-y-0.5 text-xs">
        <Figures run={run} now={now} />
      </span>

      {!calm && (
        <>
          {run.status === 'running' ? (
            <StageSegments run={run} steps={null} now={now} className="mt-2" />
          ) : (
            <StageSegments run={run} steps={null} now={now} bar={false} className="mt-1" />
          )}
          {run.status_message && (
            <Msg tone={msgTone} className="mt-1.5">
              {run.status_message}
            </Msg>
          )}
        </>
      )}
    </button>
  )
})

function Figure({ value, label }: { value: string; label?: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className={clsx(MONO, 'text-foreground font-medium')}>{value}</span>
      {label && <> {label}</>}
    </span>
  )
}

/** Fetched, passed (with percent), duration or elapsed; cost and tokens only once a run is done. */
function Figures({ run, now }: { run: PipelineRun; now: string }) {
  if (run.status === 'pending') {
    return (
      <>
        <span>queued {run.started_at ? relativeAge(run.started_at, now) : '—'}</span>
        <Figure value={formatUsd(run.usd_cost)} />
      </>
    )
  }
  const pct = percentOf(run.total_papers_passed_screening, run.total_papers_fetched)
  return (
    <>
      <Figure value={String(run.total_papers_fetched)} label="fetched" />
      <Figure
        value={String(run.total_papers_passed_screening)}
        label={pct === null ? 'passed' : `passed · ${pct}%`}
      />
      {run.status === 'running' ? (
        <span className="whitespace-nowrap">
          elapsed{' '}
          <span className={clsx(MONO, 'text-foreground font-medium')}>
            {run.started_at ? elapsed(run.started_at, now) : '—'}
          </span>
        </span>
      ) : (
        <Figure value={formatDuration(run.duration_seconds)} />
      )}
      {run.status === 'completed' && (
        <>
          <Figure value={formatUsd(run.usd_cost)} />
          <Figure value={formatTokens(run.total_tokens)} label="tokens" />
        </>
      )}
    </>
  )
}

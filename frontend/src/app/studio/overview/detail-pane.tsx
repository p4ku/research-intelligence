'use client'

/**
 * The right pane: one run in full. Sticky head with the permalink and the
 * close/back control, then Status, Steps, Run facts and Edition. Everything
 * on the run row renders at once; steps and the edition arrive on demand.
 */
import { Link } from '@/components/link'
import { Bone } from '@/components/skeleton'
import type { Edition } from '@/lib/bff/briefings/schema'
import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import { stageLabel, type PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import { ArrowTopRightOnSquareIcon, ChevronLeftIcon, XMarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { forwardRef } from 'react'
import { formatDuration, formatTokens, formatUsd, shortId } from '../run-presentation'
import {
  editionDateOf,
  elapsed,
  fmtUtc,
  percentOf,
  relativeAge,
  runMarks,
  triggerText,
  type RunIndex,
} from './derive'
import { EditionBlock } from './edition-block'
import type { Loadable } from './loadable'
import { Chip, FOCUS, MONO, Msg, Slab, StatusChip } from './primitives'
import { StageSegments } from './stage-segments'
import { StepSpine, StepSpineSkeleton } from './step-spine'

const HEAD = 'border-line bg-surface border-b px-4 pt-3 pb-2.5 lg:sticky lg:top-0 lg:z-[5]'
const CLOSE =
  'border-line text-muted-foreground hover:bg-foreground/3 hover:text-foreground inline-flex shrink-0 items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11.5px] transition-colors duration-150 max-sm:min-h-11 max-sm:px-2.5'

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      data-row="fact"
      className="border-line-soft grid grid-cols-1 gap-x-2.5 gap-y-0.5 border-b py-1.5 text-[12.5px] min-[440px]:grid-cols-[minmax(96px,38%)_minmax(0,1fr)] min-[440px]:items-baseline"
    >
      <dt className="text-muted-foreground text-[11.5px]">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

export interface DetailPaneProps {
  run: PipelineRun
  workspace: WorkspaceSummary | undefined
  index: RunIndex
  steps: Loadable<ComponentRun[]>
  edition: Loadable<Edition | null>
  now: string
  /** The run vanished from the last refresh; the pane keeps showing what it had. */
  stale: boolean
  currentWorkspaceId: string | null
  onClose: () => void
  onScope: (id: string) => void
}

export const DetailPane = forwardRef<HTMLHeadingElement, DetailPaneProps>(function DetailPane(
  { run, workspace, index, steps, edition, now, stale, currentWorkspaceId, onClose, onScope },
  titleRef,
) {
  const bad = run.status === 'failed' || run.status === 'aborted'
  const msgTone = bad ? 'neg' : run.status === 'running' ? 'acc' : 'mut'
  const pct = percentOf(run.total_papers_passed_screening, run.total_papers_fetched)
  const loadedSteps = steps.status === 'ready' ? steps.data : null
  const marks = runMarks(run, index)
  const day = editionDateOf(run)
  const dayOwner =
    (index.byWorkspace.get(run.workspace_id) ?? []).find(
      (r) => r.status === 'completed' && editionDateOf(r) === day,
    ) ?? null

  return (
    <div data-shape="run-pane">
      <div className={HEAD}>
        <div className="flex items-start gap-2.5 max-sm:items-center">
          <h2
            ref={titleRef}
            id="run-detail-title"
            tabIndex={-1}
            className="min-w-0 flex-1 text-[15px] leading-tight font-semibold break-words outline-none"
          >
            Run{' '}
            <span className={clsx(MONO, 'text-muted-foreground text-[13px] font-normal')}>
              {shortId(run.id)}
            </span>
          </h2>
          <Link
            href={`/studio/runs/${run.id}`}
            className={clsx(CLOSE, FOCUS)}
            title={`Run ${run.id}`}
          >
            <ArrowTopRightOnSquareIcon aria-hidden="true" className="size-3.5" />
            Open run page
          </Link>
          <button type="button" onClick={onClose} className={clsx(CLOSE, FOCUS)}>
            <XMarkIcon aria-hidden="true" className="hidden size-3.5 lg:block" />
            <ChevronLeftIcon aria-hidden="true" className="size-3.5 lg:hidden" />
            <span className="hidden lg:inline">Close</span>
            <span className="lg:hidden">Back</span>
          </button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <StatusChip status={run.status} />
          {marks.length > 0 && <Chip tone="plain">{marks.join(' · ')}</Chip>}
          {stale && <Chip tone="warn">No longer listed</Chip>}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          {workspace ? (
            <button
              type="button"
              onClick={() => onScope(workspace.id)}
              className={clsx(
                FOCUS,
                'text-accent-ink text-[11.5px] break-words underline underline-offset-2',
              )}
            >
              {run.workspace_name}
            </button>
          ) : (
            <span className="text-[11.5px] break-words">
              {run.workspace_name}{' '}
              <span className="text-muted-foreground">(not in your workspace list)</span>
            </span>
          )}
          <span className={clsx(MONO, 'text-muted-foreground text-[11.5px]')}>
            {run.status === 'pending' ? 'queued ' : ''}
            {run.started_at ? fmtUtc(run.started_at) : 'no start time'}
          </span>
        </div>
      </div>

      <div className="px-4 py-4">
        {/* -------------------------------- status ------------------------------- */}
        <section className="mb-5">
          <Slab className="mb-2">Status</Slab>
          {run.status_message ? (
            <Msg tone={msgTone}>{run.status_message}</Msg>
          ) : (
            <Msg tone="mut">The engine left no status message.</Msg>
          )}
          <StageSegments
            run={run}
            steps={loadedSteps}
            now={now}
            bar={run.status !== 'completed' && run.status !== 'pending'}
            className="mt-2.5"
          />
        </section>

        {/* -------------------------------- steps -------------------------------- */}
        <section className="mb-5">
          <Slab
            className="mb-2"
            count={steps.status === 'ready' ? `${steps.data.length} recorded` : undefined}
          >
            Steps
          </Slab>
          <StepSpine run={run} steps={steps} now={now} />
        </section>

        {/* -------------------------------- facts -------------------------------- */}
        <section className="mb-5">
          <Slab className="mb-2">Run facts</Slab>
          <dl className="border-line-soft border-t" data-shape="run-pane-facts">
            <Fact label={run.status === 'pending' ? 'Queued' : 'Started'}>
              <span className={MONO}>{run.started_at ? fmtUtc(run.started_at) : '—'}</span>
            </Fact>
            <Fact label="Completed">
              {run.completed_at ? (
                <span className={MONO}>{fmtUtc(run.completed_at)}</span>
              ) : (
                <span className="text-muted-foreground">
                  {run.status === 'running'
                    ? `— still running, started ${run.started_at ? relativeAge(run.started_at, now) : '—'}`
                    : run.status === 'pending'
                      ? '— queued, not started'
                      : '— no completion time recorded'}
                </span>
              )}
            </Fact>
            <Fact label="Duration">
              <span className={MONO}>{formatDuration(run.duration_seconds)}</span>
              {run.duration_seconds === null && run.status === 'running' && run.started_at && (
                <span className="text-muted-foreground">
                  {' '}
                  (elapsed <span className={MONO}>{elapsed(run.started_at, now)}</span>)
                </span>
              )}
            </Fact>
            <Fact label="Cost">
              <span className={MONO}>{formatUsd(run.usd_cost)}</span>
            </Fact>
            <Fact label="Tokens in / out">
              <span className={MONO}>{formatTokens(run.tokens_in)}</span> /{' '}
              <span className={MONO}>{formatTokens(run.tokens_out)}</span>{' '}
              <span className="text-muted-foreground">
                (<span className={MONO}>{formatTokens(run.total_tokens)}</span> total)
              </span>
            </Fact>
            <Fact label="Trigger">{triggerText(run)}</Fact>
            <Fact label="Reprocess mode">
              {run.reprocess_existing ? 'On — existing papers reprocessed' : 'Off'}
            </Fact>
            <Fact label="Last stage dispatched">
              {run.current_stage ? (
                <>
                  {stageLabel(run.current_stage)}{' '}
                  <span className={clsx(MONO, 'text-muted-foreground')}>{run.current_stage}</span>
                </>
              ) : (
                '—'
              )}
            </Fact>
            <Fact label="Papers">
              <span className={MONO}>{run.total_papers_passed_screening}</span> of{' '}
              <span className={MONO}>{run.total_papers_fetched}</span> passed screening
              {pct !== null && (
                <>
                  {' '}
                  <span className={MONO}>({pct}%)</span>
                </>
              )}
            </Fact>
            <Fact label="Run id">
              <span className={clsx(MONO, 'break-all')}>{run.id}</span>
            </Fact>
          </dl>
        </section>

        {/* ------------------------------- edition ------------------------------- */}
        <section>
          <Slab className="mb-2">Edition</Slab>
          <EditionBlock
            run={run}
            edition={edition}
            dayOwner={dayOwner}
            inCurrentWorkspace={currentWorkspaceId === run.workspace_id}
          />
        </section>
      </div>
    </div>
  )
})

/** Head, status, four step rows and the facts list as bones. */
export function DetailPaneSkeleton({ steps = 4 }: { steps?: number }) {
  return (
    <div data-shape="run-pane" data-state="skeleton">
      <div className={HEAD}>
        <div className="flex items-start gap-2.5 max-sm:items-center">
          <h2 className="min-w-0 flex-1 text-[15px] leading-tight font-semibold">
            <Bone.Text widths={['12ch']} />
          </h2>
          {/* The controls keep their real box so the head is the same height. */}
          {['12ch', '5ch'].map((w) => (
            <span key={w} className={CLOSE}>
              <Bone.Text widths={[w]} />
            </span>
          ))}
        </div>
        <div className="mt-1.5 flex gap-1.5">
          <Bone.Chip width={80} className="h-[19px]" />
        </div>
        <div className="mt-1.5 flex gap-2 text-[11.5px]">
          <Bone.Text widths={['16ch']} />
          <Bone.Text widths={['20ch']} />
        </div>
      </div>
      <div className="px-4 py-4">
        <section className="mb-5">
          <Slab as="div" className="mb-2">
            Status
          </Slab>
          {/* Status messages are sentences; at pane width they take two lines. */}
          <Msg tone="mut">
            <Bone.Text lines={2} widths={['100%', '45%']} />
          </Msg>
          {/* StageSegments adds its own mt-1.5 under the section's mt-2.5. */}
          <Bone.Text widths={['60%']} className="mt-4 text-xs" />
        </section>
        <section className="mb-5">
          <Slab as="div" className="mb-2">
            Steps
          </Slab>
          <StepSpineSkeleton rows={steps} />
        </section>
        <section className="mb-5">
          <Slab as="div" className="mb-2">
            Run facts
          </Slab>
          <dl className="border-line-soft border-t" data-shape="run-pane-facts">
            {[
              'Started',
              'Completed',
              'Duration',
              'Cost',
              'Tokens in / out',
              'Trigger',
              'Reprocess mode',
              'Last stage dispatched',
              'Papers',
              'Run id',
            ].map((label, i) => (
              <Fact key={label} label={label}>
                {/* A uuid wraps to two lines at pane width. */}
                {i === 9 ? (
                  <Bone.Text lines={2} widths={['100%', '40%']} />
                ) : (
                  <Bone.Text widths={['14ch']} />
                )}
              </Fact>
            ))}
          </dl>
        </section>
        <section>
          <Slab as="div" className="mb-2">
            Edition
          </Slab>
          <Msg tone="mut">
            <Bone.Text widths={['55%']} />
          </Msg>
        </section>
      </div>
    </div>
  )
}

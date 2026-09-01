import { Breadcrumbs, Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { componentRuns as componentRunsService } from '@/lib/bff/component-runs/service'
import { forPage } from '@/lib/bff/core/page'
import { ProblemError } from '@/lib/bff/core/problem'
import { stageLabel } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { formatDuration, formatTokens, formatUsd, RunStatus } from '../../run-presentation'
import { StepTimeline } from './step-timeline'

export const metadata: Metadata = { title: 'Run' }
export const dynamic = 'force-dynamic'

function shortId(id: string): string {
  return id.slice(0, 8)
}

function Fact({
  label,
  sub,
  children,
}: {
  label: string
  sub?: string
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium tracking-[0.12em] text-zinc-400 uppercase dark:text-zinc-500">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-zinc-900 dark:text-zinc-100">
        <span className="block truncate">{children}</span>
        {sub && (
          <span className="mt-0.5 block truncate text-xs text-zinc-400 dark:text-zinc-500">
            {sub}
          </span>
        )}
      </dd>
    </div>
  )
}

/**
 * UTC, explicitly — see the note in `../page.tsx`. Server components would
 * otherwise format in the server's zone and pass it off as the reader's.
 */
function timestampUtc(iso: string | null): string {
  if (!iso) return '—'
  return `${new Date(iso).toLocaleString('en-GB', {
    timeZone: 'UTC',
    dateStyle: 'medium',
    timeStyle: 'short',
    hour12: false,
  })} UTC`
}

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, workspace] = await Promise.all([params, getCurrentWorkspace()])

  // `forPage` sends an expired session through the logout flow; the 404 catch
  // inside it turns an unknown (or non-member) run id into a proper not-found
  // rather than an error card.
  const [run, steps] = await forPage(
    Promise.all([
      runsService.get(id).catch((error: unknown) => {
        if (error instanceof ProblemError && error.problem.status === 404) notFound()
        throw error
      }),
      componentRunsService.listAll(id).catch((error: unknown) => {
        if (error instanceof ProblemError && error.problem.status === 404) return []
        throw error
      }),
    ]),
  )

  // Any run id is reachable by URL, so it can belong to a workspace other than
  // the one the sidebar is showing. Say so rather than letting the chrome imply
  // the run belongs to the selected workspace.
  const foreign = workspace !== null && workspace.id !== run.workspace_id
  const started = timestampUtc(run.started_at)

  const failedSteps = steps.filter(
    (step) => step.status === 'failed' || step.status === 'aborted',
  )

  // Only steps that recorded spend contribute; the rest are genuinely unmeasured.
  const stepSpend = steps.reduce((sum, step) => sum + (step.cost.usd ?? 0), 0)
  const unattributed = run.usd_cost - stepSpend

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: 'Studio', href: '/studio/runs' },
          { label: 'Runs', href: '/studio/runs' },
          { label: shortId(run.id) },
        ]}
      />

      <PageHeader
        eyebrow={run.workspace_name}
        title={`Run ${shortId(run.id)}`}
        description={run.status_message ?? undefined}
        actions={<RunStatus run={run} />}
      />

      {foreign && (
        <div className="rounded-sm border border-amber-300/60 bg-amber-50 p-4 dark:border-amber-400/25 dark:bg-amber-400/10">
          <p className="text-sm text-amber-900 dark:text-amber-200">
            This run belongs to <strong>{run.workspace_name}</strong>, not the workspace selected in
            the sidebar. Switch workspace to see it in the runs list.
          </p>
        </div>
      )}

      {failedSteps.length > 0 && (
        <div className="rounded-sm border border-red-300/60 bg-red-50 p-4 dark:border-red-400/25 dark:bg-red-500/10">
          <p className="text-sm font-medium text-red-900 dark:text-red-200">
            {failedSteps.length} step{failedSteps.length === 1 ? '' : 's'} did not succeed:{' '}
            {failedSteps.map((step) => step.label).join(', ')}.
          </p>
        </div>
      )}

      <StatBand
        flow
        items={[
          { label: 'Fetched', value: run.total_papers_fetched, sub: 'from the sources' },
          {
            label: 'Passed screening',
            value: run.total_papers_passed_screening,
            sub:
              run.total_papers_fetched > 0
                ? `${Math.round((run.total_papers_passed_screening / run.total_papers_fetched) * 100)}% of fetched`
                : undefined,
          },
          { label: 'Papers stored', value: run.papers_count, sub: 'rows in this run' },
          { label: 'Extractions', value: run.extractions_count, sub: 'parameter values' },
        ]}
      />

      <Card>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
          <Fact label="Started">{started}</Fact>
          <Fact label="Duration">{formatDuration(run.duration_seconds)}</Fact>
          <Fact label="Cost">{formatUsd(run.usd_cost)}</Fact>
          <Fact
            label="Tokens"
            sub={`${formatTokens(run.tokens_in)} in · ${formatTokens(run.tokens_out)} out`}
          >
            {formatTokens(run.total_tokens)}
          </Fact>
          <Fact label="Triggered by">
            {run.triggered_by ?? <span className="text-zinc-400">System</span>}
          </Fact>
          <Fact label="Mode">
            {run.reprocess_existing ? 'Reprocess existing' : 'Skip duplicates'}
          </Fact>
          {/* Reported, not interpreted: `current_stage` is the last stage the
              engine dispatched, and a rerun rewrites it to the re-triggered
              step. The timeline below is the evidence of what actually ran. */}
          <Fact label="Last stage dispatched">
            {run.current_stage ? stageLabel(run.current_stage) : '—'}
          </Fact>
          {run.duplicates_count > 0 && (
            <Fact label="Duplicates">{run.duplicates_count.toLocaleString('en-US')}</Fact>
          )}
          {run.storage && (
            <Fact
              label="Artefacts"
              sub={`${run.storage.files} file${run.storage.files === 1 ? '' : 's'}`}
            >
              {run.storage.size_formatted}
            </Fact>
          )}
        </dl>
      </Card>

      <section className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel>Steps</SectionLabel>
          {steps.length > 0 && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {steps.length} step{steps.length === 1 ? '' : 's'} · {formatUsd(stepSpend)} attributed
              {/* A gap here means spend the engine booked on the run but not on
                  any step — worth seeing rather than silently absorbing. */}
              {Math.abs(unattributed) >= 0.0001 && (
                <span className="text-amber-700 dark:text-amber-400">
                  {' · '}
                  {formatUsd(unattributed)} unattributed
                </span>
              )}
            </p>
          )}
        </div>

        {steps.length === 0 ? (
          <Card>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No steps recorded for this run.
            </p>
          </Card>
        ) : (
          <Card className="py-1">
            <StepTimeline steps={steps} />
          </Card>
        )}
      </section>
    </div>
  )
}

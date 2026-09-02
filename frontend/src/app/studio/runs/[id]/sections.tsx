import { Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { componentRuns as componentRunsService } from '@/lib/bff/component-runs/service'
import { forPage } from '@/lib/bff/core/page'
import { ProblemError } from '@/lib/bff/core/problem'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import { notFound } from 'next/navigation'
import { formatUsd, RunStatus, shortId } from '../../run-presentation'
import { RunFacts } from './run-facts'
import { StepTimeline } from './step-timeline'

/**
 * The run page's streamed sections: one async Server Component per Suspense
 * boundary, each awaiting only its own data. Both services are React-cached,
 * so the run the head fetches is the same promise the steps section reads for
 * the spend line — one upstream call each.
 *
 * `forPage` sends an expired session through the logout flow; the 404 catch
 * turns an unknown (or non-member) run id into the segment's not-found page.
 * The status code is 200 once streaming has begun (the shell went out with
 * loading.tsx); the page is behind auth, so nothing indexes it either way.
 */
function getRun(id: string) {
  return runsService.get(id).catch((error: unknown) => {
    if (error instanceof ProblemError && error.problem.status === 404) notFound()
    throw error
  })
}

function getSteps(id: string) {
  return componentRunsService.listAll(id).catch((error: unknown) => {
    if (error instanceof ProblemError && error.problem.status === 404) return []
    throw error
  })
}

/** Header, workspace notice, funnel band and the facts card — everything the run record alone gives. */
export async function RunHead({ id }: { id: string }) {
  // The workspace is fetched here, in parallel with the run, rather than by
  // the page: this is the one section that reads it, and awaiting it above
  // the Suspense boundaries kept the whole shell behind loading.tsx.
  const [run, workspace] = await Promise.all([forPage(getRun(id)), getCurrentWorkspace()])

  // Any run id is reachable by URL, so it can belong to a workspace other than
  // the one the sidebar is showing. Say so rather than letting the chrome imply
  // the run belongs to the selected workspace.
  const foreign = workspace !== null && workspace.id !== run.workspace_id

  return (
    <div className="space-y-8">
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
        <RunFacts run={run} />
      </Card>
    </div>
  )
}

/** The failed-steps notice and the timeline — everything that needs the step list. */
export async function Steps({ id }: { id: string }) {
  const [run, steps] = await forPage(Promise.all([getRun(id), getSteps(id)]))

  const failedSteps = steps.filter((step) => step.status === 'failed' || step.status === 'aborted')

  // Only steps that recorded spend contribute; the rest are genuinely unmeasured.
  const stepSpend = steps.reduce((sum, step) => sum + (step.cost.usd ?? 0), 0)
  const unattributed = run.usd_cost - stepSpend

  return (
    <div className="space-y-8">
      {failedSteps.length > 0 && (
        <div className="rounded-sm border border-red-300/60 bg-red-50 p-4 dark:border-red-400/25 dark:bg-red-500/10">
          <p className="text-sm font-medium text-red-900 dark:text-red-200">
            {failedSteps.length} step{failedSteps.length === 1 ? '' : 's'} did not succeed:{' '}
            {failedSteps.map((step) => step.label).join(', ')}.
          </p>
        </div>
      )}

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

import { Breadcrumbs, Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { componentRuns as componentRunsService } from '@/lib/bff/component-runs/service'
import { ProblemError } from '@/lib/bff/core/problem'
import { haltedStage, stageLabel } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { getLang } from '@/lib/i18n-server'
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

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, lang] = await Promise.all([params, getLang()])

  // A 401 is handled by `forPage` elsewhere; here a bad id is the likely
  // failure, and it should read as "no such run", not as a crash.
  const [run, steps] = await Promise.all([
    runsService.get(id).catch((error: unknown) => {
      if (error instanceof ProblemError && error.problem.status === 404) notFound()
      throw error
    }),
    componentRunsService.listAll(id).catch((error: unknown) => {
      if (error instanceof ProblemError && error.problem.status === 404) return []
      throw error
    }),
  ])

  const halted = haltedStage(run)
  const started = run.started_at
    ? new Date(run.started_at).toLocaleString(lang === 'de' ? 'de-DE' : 'en-US', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '—'

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

      {halted && (
        <div className="rounded-sm border border-amber-300/60 bg-amber-50 p-4 dark:border-amber-400/25 dark:bg-amber-400/10">
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
            This run closed at {stageLabel(halted).toLowerCase()}, before the final stage.
          </p>
          <p className="mt-1 text-sm text-amber-800/90 dark:text-amber-200/80">
            Django records it as <code className="font-mono text-[13px]">completed</code> because
            the engine stopped cleanly — no new papers, an exhausted quota or a guard tripping all
            look like this. The stages after {stageLabel(halted).toLowerCase()} never ran.
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

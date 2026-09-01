import { Card, PageHeader, StatBand } from '@/components/scanner-ui'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import { forPage } from '@/lib/bff/core/page'
import { haltedStage, type PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { getLang } from '@/lib/i18n-server'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import clsx from 'clsx'
import type { Metadata } from 'next'
import Link from 'next/link'
import { formatDuration, formatUsd, RunStatus as RunStatusPill } from '../run-presentation'

export const metadata: Metadata = { title: 'Runs' }
export const dynamic = 'force-dynamic'

/** Tabs are derived, not queried: Django has no "halted" status to filter on. */
type Tab = 'all' | 'completed' | 'halted' | 'failed' | 'running'

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running' },
  { key: 'completed', label: 'Completed' },
  { key: 'halted', label: 'Halted' },
  { key: 'failed', label: 'Failed' },
]

function matches(run: PipelineRun, tab: Tab): boolean {
  const halted = haltedStage(run) !== null
  switch (tab) {
    case 'all':
      return true
    case 'halted':
      return halted
    case 'completed':
      return run.status === 'completed' && !halted
    case 'failed':
      return run.status === 'failed' || run.status === 'aborted'
    case 'running':
      return run.status === 'running' || run.status === 'pending'
  }
}

/** Local wall-clock stamp; runs are compared against each other, not read as prose. */
function timestamp(iso: string | null, lang: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(lang === 'de' ? 'de-DE' : 'en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>
}) {
  const [{ status }, ws, lang] = await Promise.all([searchParams, getCurrentWorkspace(), getLang()])
  const tab: Tab = TABS.some((candidate) => candidate.key === status) ? (status as Tab) : 'all'

  if (!ws) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow="Studio" title="Runs" />
        <Card>
          <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
            No workspace selected
          </p>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Pick a workspace to review its pipeline runs.
          </p>
        </Card>
      </div>
    )
  }

  const all = await forPage(runsService.listAll(ws.id))
  const shown = all.filter((run) => matches(run, tab))

  const haltedCount = all.filter((run) => haltedStage(run) !== null).length
  const fetched = all.reduce((sum, run) => sum + run.total_papers_fetched, 0)
  const passed = all.reduce((sum, run) => sum + run.total_papers_passed_screening, 0)
  const spend = all.reduce((sum, run) => sum + run.usd_cost, 0)

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={ws.name}
        title="Runs"
        description="Every pipeline run in this workspace — what it produced, what it cost, and where it stopped."
      />

      <StatBand
        items={[
          { label: 'Runs', value: all.length },
          {
            label: 'Halted early',
            value: haltedCount,
            sub: haltedCount > 0 ? 'finished before the last stage' : 'all ran to completion',
          },
          {
            label: 'Passed screening',
            value: passed.toLocaleString('en-US'),
            sub:
              fetched > 0
                ? `${Math.round((passed / fetched) * 100)}% of ${fetched.toLocaleString('en-US')} fetched`
                : undefined,
          },
          { label: 'Total spend', value: formatUsd(spend) },
        ]}
      />

      <nav className="flex flex-wrap items-center gap-1" aria-label="Filter runs by outcome">
        {TABS.map(({ key, label }) => {
          const count = all.filter((run) => matches(run, key)).length
          const isCurrent = key === tab
          return (
            <Link
              key={key}
              href={key === 'all' ? '/studio/runs' : `/studio/runs?status=${key}`}
              aria-current={isCurrent ? 'page' : undefined}
              className={clsx(
                'rounded-sm px-2.5 py-1 text-xs font-medium transition-colors',
                isCurrent
                  ? 'bg-zinc-950 text-white dark:bg-white dark:text-zinc-950'
                  : 'text-zinc-500 hover:bg-zinc-950/5 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-zinc-100',
              )}
            >
              {label}
              <span className={clsx('ml-1.5 tabular-nums', !isCurrent && 'text-zinc-400')}>
                {count}
              </span>
            </Link>
          )
        })}
      </nav>

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {all.length === 0
              ? `No pipeline runs in ${ws.name} yet.`
              : `No ${tab} runs. ${all.length} run${all.length === 1 ? '' : 's'} in total.`}
          </p>
        </Card>
      ) : (
        <Table dense>
          <TableHead>
            <TableRow>
              <TableHeader>Started</TableHeader>
              <TableHeader>Outcome</TableHeader>
              <TableHeader className="text-right">Fetched</TableHeader>
              <TableHeader className="text-right">Passed</TableHeader>
              <TableHeader className="text-right">Duration</TableHeader>
              <TableHeader className="text-right">Cost</TableHeader>
              <TableHeader>Summary</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {shown.map((run) => (
              <TableRow key={run.id} href={`/studio/runs/${run.id}`} title={`Run ${run.id}`}>
                <TableCell className="font-medium tabular-nums">
                  {timestamp(run.started_at, lang)}
                </TableCell>
                <TableCell>
                  <RunStatusPill run={run} />
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {run.total_papers_fetched.toLocaleString('en-US')}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {run.total_papers_passed_screening.toLocaleString('en-US')}
                </TableCell>
                <TableCell className="text-right tabular-nums text-zinc-500 dark:text-zinc-400">
                  {formatDuration(run.duration_seconds)}
                </TableCell>
                <TableCell className="text-right tabular-nums text-zinc-500 dark:text-zinc-400">
                  {formatUsd(run.usd_cost)}
                </TableCell>
                <TableCell className="max-w-md truncate text-zinc-500 dark:text-zinc-400">
                  {run.status_message ?? '—'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

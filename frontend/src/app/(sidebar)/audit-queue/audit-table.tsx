'use client'

import { Button } from '@/components/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import type { AuditGate, AuditQueueItem, AuditStatus } from '@/lib/bff/audit/schema'
import clsx from 'clsx'
import { useMemo, useState } from 'react'

function gateLabel(gate: AuditGate): string {
  switch (gate) {
    case 'abstract_screening':
      return 'Abstract screening'
    case 'full_text_screening':
      return 'Full-text screening'
    case 'parameter_extraction':
      return 'Parameter extraction'
    default:
      return gate
  }
}

function StatusPill({ status }: { status: AuditStatus }) {
  const styles: Record<AuditStatus, string> = {
    pending:
      'bg-amber-50 text-amber-900 ring-amber-600/25 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25',
    in_review:
      'bg-blue-50 text-blue-800 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-400/20',
    completed:
      'bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20',
  }

  const labels: Record<AuditStatus, string> = {
    pending: 'Pending',
    in_review: 'In review',
    completed: 'Completed',
  }

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-sm px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset',
        styles[status],
      )}
    >
      {labels[status]}
    </span>
  )
}

function ProgressBar({ completed, total }: { completed: number; total: number }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0
  return (
    <div className="w-32">
      <div className="flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
        <span>
          {completed}/{total}
        </span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
        <div
          className={clsx(
            'h-full transition-all duration-300',
            pct === 100 ? 'bg-emerald-500' : 'bg-blue-500',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function AuditTable({ items }: { items: AuditQueueItem[] }) {
  const [tab, setTab] = useState<'pending' | 'all' | 'completed'>('pending')

  const { pendingItems, completedItems } = useMemo(() => {
    const pending: AuditQueueItem[] = []
    const completed: AuditQueueItem[] = []
    for (const item of items) {
      if (item.status === 'completed') {
        completed.push(item)
      } else {
        pending.push(item)
      }
    }
    return { pendingItems: pending, completedItems: completed }
  }, [items])

  const displayedItems =
    tab === 'pending' ? pendingItems : tab === 'completed' ? completedItems : items

  return (
    <div className="space-y-4">
      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-zinc-200 pb-2 dark:border-zinc-800">
        <button
          type="button"
          onClick={() => setTab('pending')}
          className={clsx(
            'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
            tab === 'pending'
              ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
              : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
          )}
        >
          My Pending ({pendingItems.length})
        </button>
        <button
          type="button"
          onClick={() => setTab('all')}
          className={clsx(
            'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
            tab === 'all'
              ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
              : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
          )}
        >
          All Assigned ({items.length})
        </button>
        <button
          type="button"
          onClick={() => setTab('completed')}
          className={clsx(
            'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
            tab === 'completed'
              ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
              : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
          )}
        >
          Completed History ({completedItems.length})
        </button>
      </div>

      {/* Table */}
      {displayedItems.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-white p-12 text-center dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {tab === 'pending'
              ? 'No pending audits assigned to you.'
              : tab === 'completed'
                ? 'No completed audits yet.'
                : 'No audit cohorts found.'}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Briefing / Workspace</TableHeader>
                <TableHeader>Pipeline Run</TableHeader>
                <TableHeader>Audit Gate</TableHeader>
                <TableHeader>Progress</TableHeader>
                <TableHeader className="text-right">Remaining</TableHeader>
                <TableHeader>Status</TableHeader>
                <TableHeader className="text-right !pr-6 sm:!pr-6">Action</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {displayedItems.map((item) => {
                const isComplete = item.status === 'completed'
                const actionHref = `/audit-queue/${item.cohort_id}`
                return (
                  <TableRow
                    key={item.cohort_id}
                    href={actionHref}
                    title={isComplete ? `View ${item.briefing_name}` : `Review ${item.briefing_name}`}
                    className="cursor-pointer transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                  >
                    <TableCell>
                      <div className="font-medium text-zinc-900 dark:text-white">
                        {item.briefing_name}
                      </div>
                      <div className="text-xs text-zinc-500 dark:text-zinc-400">
                        {item.workspace_name}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-zinc-600 dark:text-zinc-400">
                      run-{item.pipeline_run_id.slice(0, 8)}
                    </TableCell>
                    <TableCell className="text-xs text-zinc-700 dark:text-zinc-300">
                      {gateLabel(item.gate)}
                    </TableCell>
                    <TableCell>
                      <ProgressBar completed={item.completed_count} total={item.assigned_count} />
                    </TableCell>
                    <TableCell className="text-right text-xs font-semibold text-zinc-900 tabular-nums dark:text-white">
                      {item.remaining_count}
                    </TableCell>
                    <TableCell>
                      <StatusPill status={item.status} />
                    </TableCell>
                    <TableCell className="text-right !pr-6 sm:!pr-6">
                      <div className="flex justify-end pr-2">
                        <Button
                          href={actionHref}
                          color={isComplete ? 'zinc' : 'dark/zinc'}
                          className="relative z-10 text-xs font-semibold shadow-xs"
                        >
                          {isComplete ? 'View' : 'Review →'}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

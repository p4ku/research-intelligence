import { Bone } from '@/components/skeleton'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'
import Link from 'next/link'
import type { ReactNode } from 'react'

export type Tab = 'all' | 'completed' | 'failed' | 'running'

export const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed', label: 'Failed' },
]

/** The `?status=` value as a tab, falling back to `all` for anything unknown. */
export function tabFrom(status: string | undefined): Tab {
  return TABS.some((candidate) => candidate.key === status) ? (status as Tab) : 'all'
}

export function matches(run: PipelineRun, tab: Tab): boolean {
  switch (tab) {
    case 'all':
      return true
    case 'completed':
      return run.status === 'completed'
    case 'failed':
      return run.status === 'failed' || run.status === 'aborted'
    case 'running':
      return run.status === 'running' || run.status === 'pending'
  }
}

interface TabCell {
  key: Tab
  label: string
  count: ReactNode
  /** Present on the loaded tabs; the skeleton's tabs are inert spans. */
  href?: string
  current: boolean
}

// The filter strip shared by RunTabs and RunTabsSkeleton: one set of classes,
// so the skeleton keeps the loaded strip's height and rhythm.
function RunTabsFrame({ tabs }: { tabs: TabCell[] }) {
  return (
    <nav className="flex flex-wrap items-center gap-1" aria-label="Filter runs by outcome">
      {tabs.map((tab) => {
        const className = clsx(
          'rounded-sm px-2.5 py-1 text-xs font-medium transition-colors',
          tab.current
            ? 'bg-zinc-950 text-white dark:bg-white dark:text-zinc-950'
            : 'text-zinc-500 hover:bg-zinc-950/5 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-zinc-100',
        )
        const body = (
          <>
            {tab.label}
            <span className={clsx('ml-1.5 tabular-nums', !tab.current && 'text-zinc-400')}>
              {tab.count}
            </span>
          </>
        )
        return tab.href ? (
          <Link
            key={tab.key}
            href={tab.href}
            aria-current={tab.current ? 'page' : undefined}
            className={className}
          >
            {body}
          </Link>
        ) : (
          <span key={tab.key} className={className}>
            {body}
          </span>
        )
      })}
    </nav>
  )
}

export function RunTabs({ tab, runs }: { tab: Tab; runs: PipelineRun[] }) {
  const tabs = TABS.map(
    ({ key, label }): TabCell => ({
      key,
      label,
      count: runs.filter((run) => matches(run, key)).length,
      href: key === 'all' ? '/studio/runs' : `/studio/runs?status=${key}`,
      current: key === tab,
    }),
  )
  return <RunTabsFrame tabs={tabs} />
}

/**
 * The strip's loading state: the real labels with bone counts. No tab is
 * marked current — loading.tsx cannot read the query string, and a wrong
 * guess that then flips is worse than none.
 */
export function RunTabsSkeleton() {
  const tabs = TABS.map(
    ({ key, label }): TabCell => ({
      key,
      label,
      count: <Bone.Number digits={1} />,
      current: false,
    }),
  )
  return <RunTabsFrame tabs={tabs} />
}

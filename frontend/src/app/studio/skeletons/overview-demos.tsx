'use client'

/**
 * Loaded panes for the Studio overview's three shapes. The components take
 * callbacks and refs, which a Server Component (the gallery page) cannot
 * pass, so these client wrappers supply inert ones and a fixed clock.
 * Fixture selection is deliberate: each loaded pane must match its skeleton
 * row for row (bun run skeleton:drift), so the list shows one calm day group
 * and the pane shows a completed run whose steps carry no error message.
 */
import { fixtureSteps } from '@/lib/bff/component-runs/fixtures'
import { fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { fixtureOverviewRuns, fixtureRuns } from '@/lib/bff/pipeline-runs/fixtures'
import { fixtureWorkspaces } from '@/lib/bff/workspaces/fixtures'
import { indexRuns, notices, railOrder, scopeRuns, summariseWorkspace } from '../overview/derive'
import { DetailPane } from '../overview/detail-pane'
import { Rail } from '../overview/rail'
import { RunList } from '../overview/run-list'

const NOW = '2026-09-01T09:15:00Z'
const noop = () => {}

const index = indexRuns(fixtureOverviewRuns)
const summaries = new Map(
  fixtureWorkspaces.map((ws) => [ws.id, summariseWorkspace(ws, index, NOW.slice(0, 10))]),
)

export function RailDemo() {
  return (
    <Rail
      workspaces={railOrder(fixtureWorkspaces, summaries)}
      summaries={summaries}
      all={{
        runs: index.all.length,
        live: index.all.filter((r) => r.status === 'running').length,
        anyBad: true,
        usdUsed: fixtureWorkspaces.reduce((sum, ws) => sum + ws.usd_spent, 0),
      }}
      scope="all"
      onScope={noop}
    />
  )
}

/**
 * Scope "all", filter "completed", without the same-day rerun: exactly one
 * completed run, unmarked, so the list is one slab, one day head, one row —
 * the skeleton's shape.
 */
const listRuns = fixtureOverviewRuns.filter((r) => !r.reprocess_existing)
const listIndex = indexRuns(listRuns)

export function RunListDemo() {
  return (
    <RunList
      scope="all"
      workspace={null}
      runs={scopeRuns(listIndex, 'all')}
      index={listIndex}
      summary={null}
      notices={notices(fixtureWorkspaces, summaries)}
      workspaceCount={fixtureWorkspaces.length}
      filter="completed"
      runId={null}
      now={NOW}
      truncated={false}
      onFilter={noop}
      onOpen={noop}
      onScope={noop}
      rowRef={noop}
    />
  )
}

export function DetailPaneDemo() {
  return (
    <DetailPane
      run={fixtureRuns[0]}
      workspace={fixtureWorkspace}
      index={index}
      steps={{ status: 'ready', data: fixtureSteps }}
      edition={{ status: 'ready', data: null }}
      now={NOW}
      stale={false}
      currentWorkspaceId={null}
      onClose={noop}
      onScope={noop}
    />
  )
}

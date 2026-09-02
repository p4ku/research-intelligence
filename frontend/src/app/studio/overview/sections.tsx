import { forPage } from '@/lib/bff/core/page'
import { isUuid } from '@/lib/bff/core/validate'
import { runStatus, type RunStatus } from '@/lib/bff/pipeline-runs/schema'
import { runs } from '@/lib/bff/pipeline-runs/service'
import { CommandCentre } from './command-centre'
import { defaultRun, indexRuns, scopeRuns, type Filter } from './derive'
import type { OverviewState } from './state'

/**
 * Loads everything the console needs in one call (runs across workspaces
 * plus the workspaces), validates what the URL asked for against it, and
 * decides the initial state without knowing the viewport: the open run is
 * the URL's, else the scope's attention run, and only the phone layout's
 * `level` says whether the pane is what the user sees first.
 */
export async function OverviewSection({
  ws,
  run,
  status,
  currentWorkspaceId,
}: {
  ws?: string
  run?: string
  status?: string
  currentWorkspaceId: string | null
}) {
  const overview = await forPage(runs.overview())
  const index = indexRuns(overview.runs)
  const notes: string[] = []

  let scope = 'all'
  if (ws && ws !== 'all') {
    if (isUuid(ws) && overview.workspaces.some((w) => w.id === ws)) scope = ws
    else notes.push('That workspace is not in your list, so this shows all workspaces.')
  }

  const filter: Filter =
    status && (runStatus.options as readonly string[]).includes(status)
      ? (status as RunStatus)
      : 'all'

  let runId: string | null = null
  if (run) {
    if (isUuid(run) && index.byId.has(run)) runId = run
    else notes.push('That run is not in the list; the pane opened on the run that needs attention.')
  }
  if (!runId) {
    const scoped = scopeRuns(index, scope)
    runId = defaultRun(
      filter === 'all' ? scoped : scoped.filter((r) => r.status === filter),
      overview.generated_at,
    )
  }

  const initial: OverviewState = {
    scope,
    runId,
    filter,
    level: run && runId === run ? 'detail' : 'list',
  }

  return (
    <CommandCentre
      runs={overview.runs}
      workspaces={overview.workspaces}
      truncated={overview.truncated}
      initial={initial}
      renderedAt={overview.generated_at}
      currentWorkspaceId={currentWorkspaceId}
      note={notes.length ? notes.join(' ') : null}
    />
  )
}

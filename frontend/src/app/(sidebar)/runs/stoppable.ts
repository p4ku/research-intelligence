import type { WorkspacesState } from '@/lib/workspace-server'

/** The roles Django lets start or stop a run (pipeline_runs.py: admin and manager). */
export const MANAGE_RUN_ROLES = new Set(['admin', 'manager'])
const STOP_ROLES = MANAGE_RUN_ROLES

/** The roles Django lets rerun a run from a step (admin only). */
export const RERUN_ROLES = new Set(['admin'])

/**
 * The workspaces whose runs the reader may stop. Django decides for real on
 * the POST; this only keeps the control off rows where it would be refused,
 * so a researcher is not offered a destructive confirmation they cannot
 * complete. An unknown role (`null`) is not offered either.
 */
export function stoppableWorkspaces(state: WorkspacesState): ReadonlySet<string> {
  if (state.kind !== 'ok') return new Set()
  return new Set(
    state.all.filter((ws) => ws.user_role && STOP_ROLES.has(ws.user_role)).map((ws) => ws.id),
  )
}

/** The workspaces where the reader may start a run (admin or manager only). */
export function runnableWorkspaces(state: WorkspacesState): ReadonlySet<string> {
  return stoppableWorkspaces(state)
}

/** The workspaces where the reader may rerun a run from a step (admin only). */
export function rerunWorkspaces(state: WorkspacesState): ReadonlySet<string> {
  if (state.kind !== 'ok') return new Set()
  return new Set(
    state.all.filter((ws) => ws.user_role && RERUN_ROLES.has(ws.user_role)).map((ws) => ws.id),
  )
}

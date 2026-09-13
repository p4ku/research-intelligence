import type { WorkspacesState } from '@/lib/workspace-server'

/** The roles Django lets abort a run (services/pipeline_service.py). */
const STOP_ROLES = new Set(['admin', 'manager'])

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

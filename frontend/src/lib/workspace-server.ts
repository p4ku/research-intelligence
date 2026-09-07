import 'server-only'

import { forPage } from '@/lib/bff/core/page'
import { workspaces } from '@/lib/bff/workspaces/service'
import { cache } from 'react'
import type { WorkspaceSummary } from './papers/types'

/**
 * The unified scope every page reads: all the workspaces the user belongs
 * to — "domains" in the analyst-facing copy. There is no selected workspace
 * any more; lists span every membership and name the domain per row.
 *
 * `none` (no memberships) is an account fact; `unavailable` (the list could
 * not be fetched) is an outage. Render `<WorkspaceNotice kind={...}>` for
 * both — never membership copy for an outage (error-UX audit #2).
 */
export type WorkspacesState =
  | { kind: 'ok'; all: WorkspaceSummary[] }
  | { kind: 'none' }
  | { kind: 'unavailable' }

/**
 * Deduped per request. Goes through `forPage` here, not at each call site:
 * with no workspace fetch in the shell any more this is usually a page's
 * first Django call, and a rejected session must still land on the logout
 * flow rather than the route's error boundary.
 */
export const getWorkspacesState = cache(async (): Promise<WorkspacesState> => {
  const result = await forPage(workspaces.listAllResult())
  if (!result.ok) return { kind: 'unavailable' }
  if (result.workspaces.length === 0) return { kind: 'none' }
  return { kind: 'ok', all: result.workspaces }
})

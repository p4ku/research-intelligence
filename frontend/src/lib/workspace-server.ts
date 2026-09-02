import 'server-only'

import { workspaces } from '@/lib/bff/workspaces/service'
import { cookies } from 'next/headers'
import { cache } from 'react'
import type { WorkspaceSummary } from './papers/types'
import { WORKSPACE_COOKIE } from './workspace'

export interface WorkspaceChoice {
  id: string
  name: string
}

/**
 * `none` (the user belongs to no workspace) is an account fact; `unavailable`
 * (the workspace list could not be fetched) is an outage. Pages must not
 * render membership copy for an outage — that is offense #2 of the error-UX
 * audit. Render `<WorkspaceNotice kind={...}>` for both non-ok kinds.
 */
export type WorkspaceState =
  | { kind: 'ok'; ws: WorkspaceSummary }
  | { kind: 'none' }
  | { kind: 'unavailable' }

/**
 * The workspace in scope: the cookie's choice if the user still belongs to
 * it, else their first workspace. Deduped per request.
 */
export const getWorkspaceState = cache(async (): Promise<WorkspaceState> => {
  const [result, store] = await Promise.all([workspaces.listAllResult(), cookies()])
  if (!result.ok) return { kind: 'unavailable' }
  const all = result.workspaces
  if (all.length === 0) return { kind: 'none' }
  const chosen = store.get(WORKSPACE_COOKIE)?.value
  return { kind: 'ok', ws: all.find((w) => w.id === chosen) ?? all[0] }
})

/** State collapsed to a nullable — for call sites that treat both non-ok kinds alike. */
export async function getCurrentWorkspace(): Promise<WorkspaceSummary | null> {
  const state = await getWorkspaceState()
  return state.kind === 'ok' ? state.ws : null
}

/** The switcher is chrome: on an outage it degrades to an empty list quietly. */
export async function listWorkspaceChoices(): Promise<WorkspaceChoice[]> {
  const result = await workspaces.listAllResult()
  return result.ok ? result.workspaces.map((w) => ({ id: w.id, name: w.name })) : []
}

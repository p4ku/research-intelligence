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
 * The workspace in scope: the cookie's choice if the user still belongs to
 * it, else their first workspace, else null (no memberships).
 */
export const getCurrentWorkspace = cache(async (): Promise<WorkspaceSummary | null> => {
  const [all, store] = await Promise.all([workspaces.listAllSafe(), cookies()])
  if (all.length === 0) return null
  const chosen = store.get(WORKSPACE_COOKIE)?.value
  return all.find((w) => w.id === chosen) ?? all[0]
})

export async function listWorkspaceChoices(): Promise<WorkspaceChoice[]> {
  return (await workspaces.listAllSafe()).map((w) => ({ id: w.id, name: w.name }))
}

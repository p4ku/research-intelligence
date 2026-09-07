/**
 * Workspaces service. Source `django`: today's `GET /api/workspaces/` (a bare
 * array spanning the user's memberships), validated and normalised into the
 * contract shape; the requested change is pagination on the same endpoint.
 * Server-only.
 */
import 'server-only'

import type { WorkspaceDTO } from '@/lib/api/types'
import { toWorkspaceSummary } from '@/lib/papers/map'
import { cache } from 'react'
import { paginate, type ListQuery, type Page } from '../core/pagination'
import type { Problem } from '../core/problem'
import { problemResult } from '../core/result'
import { workspacesSnapshot } from '../corpus/snapshot'
import type { WorkspaceSummary } from './schema'
import { isHiddenWorkspace } from './visible'

/**
 * Raw DTOs for other BFF services (papers composition needs the full
 * extraction definitions). From the user's workspaces snapshot, held across
 * requests (../corpus/snapshot.ts) apart from the heavier papers, so a page
 * that never reads papers neither waits on them nor fails with them.
 */
export const listWorkspacesRaw = cache(() => workspacesSnapshot())

export type WorkspacesResult =
  | { ok: true; workspaces: WorkspaceSummary[] }
  | { ok: false; problem: Problem }

export const workspaces = {
  /**
   * Every workspace the user belongs to, in the contract shape, minus the
   * calibration domains (./visible.ts) — this is the list the UI renders, so
   * dropping them here hides them from every surface at once. Papers
   * composition still reads `listWorkspacesRaw`, so a paper that points at a
   * hidden domain keeps its extraction definitions. Throws problems.
   */
  listAll: cache(async (): Promise<WorkspaceSummary[]> => {
    const rows = await listWorkspacesRaw()
    return rows
      .map((ws: WorkspaceDTO) => toWorkspaceSummary(ws, new Map()))
      .filter((ws) => !isHiddenWorkspace(ws.name))
  }),

  /**
   * listAll with the failure made explicit: `{ok: false, problem}` instead of
   * an empty list, so callers can tell an outage from a user with no
   * memberships. A 401 still propagates (→ logout via forPage).
   */
  async listAllResult(): Promise<WorkspacesResult> {
    const result = await problemResult(workspaces.listAll())
    return result.ok ? { ok: true, workspaces: result.value } : result
  },

  async list(query: ListQuery): Promise<Page<WorkspaceSummary>> {
    return paginate(await workspaces.listAll(), query, '/bff/workspaces')
  },

  async get(id: string): Promise<WorkspaceSummary | null> {
    return (await workspaces.listAll()).find((ws) => ws.id === id) ?? null
  },
}

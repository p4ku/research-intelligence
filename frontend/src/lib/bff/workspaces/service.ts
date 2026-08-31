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
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type ListQuery, type Page } from '../core/pagination'
import { ProblemError } from '../core/problem'
import type { WorkspaceSummary } from './schema'
import { workspaceDTO } from './upstream'

/**
 * Raw DTOs for other BFF services (papers composition needs the full
 * extraction definitions). Deduped per request.
 */
export const listWorkspacesRaw = cache(() => django('/api/workspaces/', z.array(workspaceDTO)))

export const workspaces = {
  /** Every workspace the user belongs to, in the contract shape. Throws problems. */
  listAll: cache(async (): Promise<WorkspaceSummary[]> => {
    const rows = await listWorkspacesRaw()
    return rows.map((ws: WorkspaceDTO) => toWorkspaceSummary(ws, new Map()))
  }),

  /**
   * Like listAll, but backend/network failures resolve to [] so the shell
   * still renders; a 401 still propagates (→ logout via forPage).
   */
  async listAllSafe(): Promise<WorkspaceSummary[]> {
    try {
      return await workspaces.listAll()
    } catch (error) {
      if (error instanceof ProblemError && error.problem.status !== 401) return []
      throw error
    }
  },

  async list(query: ListQuery): Promise<Page<WorkspaceSummary>> {
    return paginate(await workspaces.listAll(), query, '/bff/workspaces')
  },

  async get(id: string): Promise<WorkspaceSummary | null> {
    return (await workspaces.listAll()).find((ws) => ws.id === id) ?? null
  },
}

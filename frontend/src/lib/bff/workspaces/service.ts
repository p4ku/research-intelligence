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
import type { Problem } from '../core/problem'
import { problemResult } from '../core/result'
import type { WorkspaceSummary } from './schema'
import { workspaceDTO } from './upstream'

/**
 * Raw DTOs for other BFF services (papers composition needs the full
 * extraction definitions). Deduped per request.
 */
export const listWorkspacesRaw = cache(() => django('/api/workspaces/', z.array(workspaceDTO)))

export type WorkspacesResult =
  | { ok: true; workspaces: WorkspaceSummary[] }
  | { ok: false; problem: Problem }

export const workspaces = {
  /** Every workspace the user belongs to, in the contract shape. Throws problems. */
  listAll: cache(async (): Promise<WorkspaceSummary[]> => {
    const rows = await listWorkspacesRaw()
    return rows.map((ws: WorkspaceDTO) => toWorkspaceSummary(ws, new Map()))
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

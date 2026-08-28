/**
 * Pipeline-runs service. Source `django`: today's
 * `GET /api/pipeline-runs/?workspace=&status=` (bare array, newest first),
 * validated and trimmed to the contract shape; the requested change is
 * pagination + ordering on the same endpoint. Server-only.
 */
import 'server-only'

import type { PipelineRunDTO } from '@/lib/api/types'
import { cache } from 'react'
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { runStatus, type PipelineRun, type RunsQuery, type RunStatus } from './schema'
import { pipelineRunDTO } from './upstream'

function toRun(dto: PipelineRunDTO): PipelineRun {
  const status = (runStatus.options as readonly string[]).includes(dto.status)
    ? (dto.status as RunStatus)
    : 'pending'
  return {
    id: dto.id,
    workspace_id: dto.workspace,
    run_date: dto.run_date,
    status,
    current_stage: dto.current_stage || null,
    total_papers_fetched: dto.total_papers_fetched,
    total_papers_passed_screening: dto.total_papers_passed_screening,
    status_message: dto.status_message || null,
    started_at: dto.started_at,
    completed_at: dto.completed_at,
  }
}

export const runs = {
  /** Runs for a workspace, newest first (the two filters Django supports today). */
  listAll: cache(async (workspaceId: string, status?: RunStatus): Promise<PipelineRun[]> => {
    const params = new URLSearchParams({ workspace: workspaceId })
    if (status) params.set('status', status)
    const rows = await django(`/api/pipeline-runs/?${params}`, z.array(pipelineRunDTO))
    return rows.map(toRun)
  }),

  async list(query: RunsQuery): Promise<Page<PipelineRun>> {
    const all = await runs.listAll(query.workspace_id, query.status)
    const extra: Record<string, string> = { workspace_id: query.workspace_id }
    if (query.status) extra.status = query.status
    return paginate(all, query, '/bff/pipeline-runs', extra)
  },
}

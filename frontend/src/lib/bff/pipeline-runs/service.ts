/**
 * Pipeline-runs service. Source `django`: today's
 * `GET /api/pipeline-runs/?workspace=&status=` (bare array, newest first),
 * validated and trimmed to the contract shape; the requested change is
 * pagination + ordering on the same endpoint. Server-only.
 */
import 'server-only'

import type { PipelineRunDTO, PipelineRunDetailDTO } from '@/lib/api/types'
import { cache } from 'react'
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { assertUuid } from '../core/validate'
import { workspaces } from '../workspaces/service'
import {
  runStatus,
  type PipelineRun,
  type PipelineRunDetail,
  type RunStatus,
  type RunsOverview,
  type RunsQuery,
} from './schema'
import { pipelineRunDTO, pipelineRunDetailDTO } from './upstream'

function toRun(dto: PipelineRunDTO): PipelineRun {
  const known = (runStatus.options as readonly string[]).includes(dto.status)
  if (!known) console.warn(`[pipeline-runs] unknown run status "${dto.status}" shown as pending`)
  const status = known ? (dto.status as RunStatus) : 'pending'
  return {
    id: dto.id,
    workspace_id: dto.workspace,
    run_date: dto.run_date,
    status,
    current_stage: dto.current_stage || null,
    total_papers_fetched: dto.total_papers_fetched,
    total_papers_passed_screening: dto.total_papers_passed_screening,
    status_message: dto.status_message || null,
    duration_seconds: dto.duration_seconds,
    // DRF Decimal → string; a malformed value reads as 0 rather than NaN.
    usd_cost: Number.isFinite(Number(dto.usd_cost)) ? Number(dto.usd_cost) : 0,
    started_at: dto.started_at,
    completed_at: dto.completed_at,
    workspace_name: dto.workspace_name,
    triggered_by: dto.triggered_by_username || null,
    schedule_id: dto.schedule ?? null,
    schedule_name: dto.schedule_name ?? null,
    reprocess_existing: dto.reprocess_existing,
    tokens_in: dto.tokens_in,
    tokens_out: dto.tokens_out,
    total_tokens: dto.tokens_consumed,
  }
}

function toRunDetail(dto: PipelineRunDetailDTO): PipelineRunDetail {
  const stats = dto.storage_stats
  // The serializer's success path writes `size_bytes`; its exception fallback
  // writes `total_bytes`. Either way `size_formatted` is the display value.
  const files = typeof stats?.total_files === 'number' ? stats.total_files : 0
  return {
    ...toRun(dto),
    papers_count: dto.papers_count,
    duplicates_count: dto.duplicates_count,
    extractions_count: dto.extractions_count,
    storage: stats ? { size_formatted: stats.size_formatted, files } : null,
  }
}

export const runs = {
  /** One run in full. */
  get: cache(async (id: string): Promise<PipelineRunDetail> => {
    const dto = await django(
      `/api/pipeline-runs/${assertUuid(id, 'run id')}/`,
      pipelineRunDetailDTO,
    )
    return toRunDetail(dto)
  }),

  /** Runs for a workspace, newest first (the two filters Django supports today). */
  listAll: cache(async (workspaceId: string, status?: RunStatus): Promise<PipelineRun[]> => {
    const params = new URLSearchParams({ workspace: workspaceId })
    if (status) params.set('status', status)
    const rows = await django(`/api/pipeline-runs/?${params}`, z.array(pipelineRunDTO))
    return rows.map(toRun)
  }),

  /**
   * Every run the caller can see, across workspaces, newest first. Django
   * serves this as one unpaginated bare array when `?workspace=` is omitted;
   * superusers get the whole system.
   */
  listAcross: cache(async (status?: RunStatus): Promise<PipelineRun[]> => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    const qs = params.toString()
    const rows = await django(`/api/pipeline-runs/${qs ? `?${qs}` : ''}`, z.array(pipelineRunDTO))
    return rows.map(toRun)
  }),

  async list(query: RunsQuery): Promise<Page<PipelineRun>> {
    const all = query.workspace_id
      ? await runs.listAll(query.workspace_id, query.status)
      : await runs.listAcross(query.status)
    const extra: Record<string, string> = {}
    if (query.workspace_id) extra.workspace_id = query.workspace_id
    if (query.status) extra.status = query.status
    return paginate(all, query, '/bff/pipeline-runs', extra)
  },

  /**
   * The Studio overview's payload: runs across every workspace plus the
   * workspaces themselves, so one call refreshes rail, list and budget
   * meters together. Runs are cut at the newest OVERVIEW_CAP; the flag says so.
   */
  async overview(): Promise<RunsOverview> {
    const [all, spaces] = await Promise.all([runs.listAcross(), workspaces.listAll()])
    return {
      runs: all.slice(0, OVERVIEW_CAP),
      workspaces: spaces,
      truncated: all.length > OVERVIEW_CAP,
      generated_at: new Date().toISOString(),
    }
  },
}

/** Unpaginated upstream; the overview renders the newest this many. */
export const OVERVIEW_CAP = 500

/**
 * Pipeline-runs service. Source `django`: today's `GET /api/pipeline-runs/`
 * (bare array, newest first, scoped to the user's memberships; `?status=`
 * supported), validated and trimmed to the contract shape; the requested
 * change is pagination + ordering on the same endpoint. One fetch serves
 * every domain — per-workspace views are in-memory filters. Starting a run
 * goes through `POST /api/pipeline-runs/start/`, the autonomous trigger.
 * Server-only.
 */
import 'server-only'

import type { PipelineRunDTO, PipelineRunDetailDTO } from '@/lib/api/types'
import { cache } from 'react'
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { ledgerRequested } from '../corpus/ledger-flag'
import { assertUuid } from '../core/validate'
import { isRetryable, runPeriod } from './period'
import {
  runStatus,
  type PipelineRun,
  type PipelineRunDetail,
  type RunStatus,
  type RunsQuery,
  type StartRun,
  type StartedRun,
} from './schema'
import { pipelineRunDTO, pipelineRunDetailDTO, startRunResponseDTO } from './upstream'

function toRun(dto: PipelineRunDTO): PipelineRun {
  const status = (runStatus.options as readonly string[]).includes(dto.status)
    ? (dto.status as RunStatus)
    : 'pending'
  return {
    id: dto.id,
    workspace_id: dto.workspace,
    workspace_name: dto.workspace_name,
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
    ...runPeriod(dto.configuration_override),
    retryable: isRetryable(dto.configuration_override),
  }
}

function toRunDetail(dto: PipelineRunDetailDTO): PipelineRunDetail {
  const stats = dto.storage_stats
  // The serializer's success path writes `size_bytes`; its exception fallback
  // writes `total_bytes`. Either way `size_formatted` is the display value.
  const files = typeof stats?.total_files === 'number' ? stats.total_files : 0
  return {
    ...toRun(dto),
    triggered_by: dto.triggered_by_username || null,
    reprocess_existing: dto.reprocess_existing,
    tokens_in: dto.tokens_in,
    tokens_out: dto.tokens_out,
    total_tokens: dto.tokens_consumed,
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

  /**
   * Every run the user can see, newest first, across all their domains: one
   * call (Django scopes the list to memberships when `workspace` is omitted).
   * Always unfiltered and cached per request, so the per-domain and
   * per-status views below, the briefings composed on top of it, and the
   * corpus snapshot's version probe all share the one fetch.
   */
  listEverywhere: cache(async (): Promise<PipelineRun[]> => {
    // Before the first await: the corpus snapshot reads this flag to know the
    // ledger is in hand for this request, so its probe is free and must run.
    ledgerRequested().yes = true
    const rows = await django('/api/pipeline-runs/', z.array(pipelineRunDTO))
    return rows.map(toRun)
  }),

  /**
   * Runs for one domain, newest first — a filter over the unfiltered
   * `listEverywhere`, status included, so every page shares the one fetch
   * that also versions the corpus snapshot (../corpus/snapshot.ts).
   */
  listAll: cache(async (workspaceId: string, status?: RunStatus): Promise<PipelineRun[]> => {
    const all = await runs.listEverywhere()
    return all.filter(
      (run) => run.workspace_id === workspaceId && (status === undefined || run.status === status),
    )
  }),

  /**
   * Start an autonomous run for one domain over a search window. Django
   * creates the run as `running` and dispatches the first stage before it
   * answers, so the id returned is already in the list. Membership and
   * quota refusals come back as 403 → `forbidden`; the caller reads the
   * list again for the new row rather than trusting the envelope.
   */
  async start(input: StartRun): Promise<StartedRun> {
    const res = await django('/api/pipeline-runs/start/', startRunResponseDTO, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        workspace_id: input.workspace_id,
        start_date: input.start_date ?? null,
        end_date: input.end_date ?? null,
        n_last_days: input.lookback_days ?? null,
        autonomous: true,
      }),
    })
    return { run_id: assertUuid(res.pipeline_run_id, 'pipeline_run_id') }
  },

  async list(query: RunsQuery): Promise<Page<PipelineRun>> {
    const all = query.workspace_id
      ? await runs.listAll(query.workspace_id, query.status)
      : (await runs.listEverywhere()).filter(
          (run) => query.status === undefined || run.status === query.status,
        )
    const extra: Record<string, string> = {}
    if (query.workspace_id) extra.workspace_id = query.workspace_id
    if (query.status) extra.status = query.status
    return paginate(all, query, '/bff/pipeline-runs', extra)
  },
}

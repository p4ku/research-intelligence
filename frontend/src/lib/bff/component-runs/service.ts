/**
 * Component-runs service. Source `django`: today's
 * `GET /api/component-runs/?pipeline_run=` (bare array, newest first),
 * validated, then resolved from free-form `metrics` JSON into the typed
 * summary the contract promises.
 *
 * Metric resolution itself lives in `normalise.ts` (pure, tested against a
 * production snapshot); this module is I/O and ordering only. Server-only.
 */
import 'server-only'

import type { ComponentRunDTO } from '@/lib/api/types'
import { cache } from 'react'
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { assertUuid } from '../core/validate'
import { chronologically, labelFor, toCost, toSummary } from './normalise'
import {
  componentStatus,
  stepType,
  type ComponentRun,
  type ComponentRunsQuery,
  type ComponentStatus,
  type StepType,
} from './schema'
import { componentRunDTO } from './upstream'

function toComponentRun(dto: ComponentRunDTO): ComponentRun {
  const step = stepType.safeParse(dto.step_type)
  // An unmodelled step still belongs on the timeline, but it must not be
  // dressed up as one of the step types we do know — `metrics` is itself a
  // real step, so falling back to it would assert something false.
  const resolvedStep: StepType = step.success ? step.data : 'unknown'
  const status = componentStatus.safeParse(dto.status)
  const resolvedStatus: ComponentStatus = status.success ? status.data : 'pending'

  return {
    id: dto.id,
    pipeline_run_id: dto.pipeline_run,
    step_type: resolvedStep,
    component_name: dto.component_name,
    label: labelFor(resolvedStep, dto.component_name),
    status: resolvedStatus,
    summary: step.success
      ? toSummary(resolvedStep, dto.metrics, dto.output_data)
      : { kind: 'none' },
    cost: toCost(dto.metrics, dto.output_data),
    duration_seconds: dto.duration_seconds,
    started_at: dto.started_at,
    completed_at: dto.completed_at,
    error_message: dto.error_message || null,
    storage_path: dto.raw_storage_path || null,
  }
}

/* --------------------------------- Service -------------------------------- */

export const componentRuns = {
  /** Every step of one run, in execution order. */
  listAll: cache(async (pipelineRunId: string): Promise<ComponentRun[]> => {
    const params = new URLSearchParams({
      pipeline_run: assertUuid(pipelineRunId, 'pipeline_run_id'),
    })
    const rows = await django(`/api/component-runs/?${params}`, z.array(componentRunDTO))
    return rows.map(toComponentRun).sort(chronologically)
  }),

  async list(query: ComponentRunsQuery): Promise<Page<ComponentRun>> {
    const all = await componentRuns.listAll(query.pipeline_run_id)
    return paginate(all, query, '/bff/component-runs', { pipeline_run_id: query.pipeline_run_id })
  },
}

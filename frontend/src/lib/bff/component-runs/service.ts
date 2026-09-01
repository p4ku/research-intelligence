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
import {
  componentStatus,
  stepType,
  type ComponentRun,
  type ComponentRunsQuery,
  type ComponentStatus,
  type StepType,
} from './schema'
import { labelFor, toCost, toSummary } from './normalise'
import { componentRunDTO } from './upstream'

function toComponentRun(dto: ComponentRunDTO): ComponentRun {
  const step = stepType.safeParse(dto.step_type)
  // An unknown step still belongs on the timeline; `metrics` fails to resolve
  // and it renders as "no metrics recorded" rather than vanishing.
  const resolvedStep: StepType = step.success ? step.data : 'metrics'
  const status = componentStatus.safeParse(dto.status)
  const resolvedStatus: ComponentStatus = status.success ? status.data : 'pending'

  return {
    id: dto.id,
    pipeline_run_id: dto.pipeline_run,
    step_type: resolvedStep,
    component_name: dto.component_name,
    label: labelFor(resolvedStep, dto.component_name),
    status: resolvedStatus,
    summary: step.success ? toSummary(resolvedStep, dto.metrics, dto.output_data) : { kind: 'none' },
    cost: toCost(dto.metrics, dto.output_data),
    duration_seconds: dto.duration_seconds,
    started_at: dto.started_at,
    completed_at: dto.completed_at,
    error_message: dto.error_message || null,
    storage_path: dto.raw_storage_path || null,
  }
}

/** Execution order for a run's timeline; unknown steps sort last, stably. */
const STEP_ORDER: StepType[] = [
  'search',
  'download',
  'ocr',
  'screening',
  'extraction',
  'signal_score',
  'metrics',
  'deep_research',
  'reporting',
]

function chronologically(a: ComponentRun, b: ComponentRun): number {
  // `started_at` is the truth when both have one — it survives reruns, which
  // re-execute a single step out of its nominal position.
  if (a.started_at && b.started_at && a.started_at !== b.started_at) {
    return a.started_at < b.started_at ? -1 : 1
  }
  return STEP_ORDER.indexOf(a.step_type) - STEP_ORDER.indexOf(b.step_type)
}

/* --------------------------------- Service -------------------------------- */

export const componentRuns = {
  /** Every step of one run, in execution order. */
  listAll: cache(async (pipelineRunId: string): Promise<ComponentRun[]> => {
    const params = new URLSearchParams({ pipeline_run: pipelineRunId })
    const rows = await django(`/api/component-runs/?${params}`, z.array(componentRunDTO))
    return rows.map(toComponentRun).sort(chronologically)
  }),

  async list(query: ComponentRunsQuery): Promise<Page<ComponentRun>> {
    const all = await componentRuns.listAll(query.pipeline_run_id)
    return paginate(all, query, '/bff/component-runs', { pipeline_run_id: query.pipeline_run_id })
  },
}

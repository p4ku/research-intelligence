/**
 * OUR pipeline-run contract: the slice of a run the UI needs (funnel counters,
 * dates, status line). Django's current serializer is richer; the requested
 * endpoint may simply paginate the existing shape — the BFF trims it. Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'

export const runStatus = z
  .enum(['pending', 'running', 'completed', 'failed', 'aborted'])
  .meta({ id: 'PipelineRunStatus' })
export type RunStatus = z.infer<typeof runStatus>

export const pipelineRun = z
  .object({
    id: z.uuid(),
    workspace_id: z.uuid(),
    /** The trigger date (YYYY-MM-DD). */
    run_date: z.iso.date(),
    status: runStatus,
    current_stage: z.string().nullable(),
    total_papers_fetched: z.number().int(),
    total_papers_passed_screening: z.number().int(),
    /** The engine's one-line human summary of the run. */
    status_message: z.string().nullable(),
    /** Django computes this; null while a run is still in flight. */
    duration_seconds: z.number().nullable(),
    /** DRF serialises the Decimal as a string; the contract carries a number. */
    usd_cost: z.number(),
    started_at: z.iso.datetime({ offset: true }).nullable(),
    completed_at: z.iso.datetime({ offset: true }).nullable(),
  })
  .meta({ id: 'PipelineRun' })
export type PipelineRun = z.infer<typeof pipelineRun>

export const runsQuery = listQuery.extend({
  workspace_id: z.uuid(),
  status: runStatus.optional(),
})
export type RunsQuery = z.infer<typeof runsQuery>

export const runPage = pageSchema(pipelineRun).meta({ id: 'PipelineRunPage' })

/**
 * One run in full: the list shape plus what it produced, what it cost and
 * where its artefacts landed. Backs `/studio/runs/[id]`.
 */
export const pipelineRunDetail = pipelineRun
  .extend({
    workspace_name: z.string(),
    /** Username, or null for a scheduled/system run. */
    triggered_by: z.string().nullable(),
    reprocess_existing: z.boolean(),
    tokens_in: z.number().int(),
    tokens_out: z.number().int(),
    total_tokens: z.number().int(),
    papers_count: z.number().int(),
    duplicates_count: z.number().int(),
    extractions_count: z.number().int(),
    storage: z
      .object({ size_formatted: z.string(), files: z.number().int() })
      .nullable(),
  })
  .meta({ id: 'PipelineRunDetail' })
export type PipelineRunDetail = z.infer<typeof pipelineRunDetail>

/**
 * The stage a run stopped at, or null if it ran to the end.
 *
 * A run can carry `status: 'completed'` while `current_stage` is an earlier
 * stage — the engine stopped (no new papers, quota exhausted, a guard tripped)
 * and closed the run cleanly. 2 of the 13 runs in the 2026-09-01 production
 * snapshot look like this. Rendering those as a plain green "Completed" is the
 * single most misleading thing this UI could do, so the derivation lives here
 * and every surface that shows a run status uses it.
 */
export function haltedStage(run: Pick<PipelineRun, 'status' | 'current_stage'>): string | null {
  if (run.status !== 'completed') return null
  const stage = run.current_stage
  if (!stage || stage === 'completed' || stage === 'reporting') return null
  return stage
}

/** `full_text_screening` → `Full text screening`. */
export function stageLabel(stage: string): string {
  const words = stage.replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

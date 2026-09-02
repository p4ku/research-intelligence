/**
 * OUR pipeline-run contract: the slice of a run the UI needs (funnel counters,
 * dates, status line). Django's current serializer is richer; the requested
 * endpoint may simply paginate the existing shape — the BFF trims it. Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'
import { workspace } from '../workspaces/schema'

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
    workspace_name: z.string(),
    /** Username, or null for a scheduled/system run. */
    triggered_by: z.string().nullable(),
    /** The WorkflowSchedule that started the run; null for a manual run. */
    schedule_id: z.uuid().nullable(),
    schedule_name: z.string().nullable(),
    reprocess_existing: z.boolean(),
    tokens_in: z.number().int(),
    tokens_out: z.number().int(),
    total_tokens: z.number().int(),
  })
  .meta({ id: 'PipelineRun' })
export type PipelineRun = z.infer<typeof pipelineRun>

export const runsQuery = listQuery.extend({
  /** Omit for every run the caller can see, across workspaces. */
  workspace_id: z.uuid().optional(),
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
    papers_count: z.number().int(),
    duplicates_count: z.number().int(),
    extractions_count: z.number().int(),
    storage: z.object({ size_formatted: z.string(), files: z.number().int() }).nullable(),
  })
  .meta({ id: 'PipelineRunDetail' })
export type PipelineRunDetail = z.infer<typeof pipelineRunDetail>

/**
 * Every run the caller can see plus every workspace they belong to, in one
 * payload: what the Studio overview renders on first paint and polls for
 * afterwards. `truncated` says the newest `runs` were cut at the cap.
 */
export const runsOverview = z
  .object({
    runs: z.array(pipelineRun),
    workspaces: z.array(workspace),
    truncated: z.boolean(),
    generated_at: z.iso.datetime({ offset: true }),
  })
  .meta({ id: 'PipelineRunsOverview' })
export type RunsOverview = z.infer<typeof runsOverview>

/**
 * The stages a run passes through, in the order the engine dispatches them
 * (the component-run timeline of a production run: search, download, OCR,
 * then screening), as the overview draws them. `PipelineRun.current_stage`
 * also takes `screening`, `metrics`, `deep_research` and `completed`; those
 * are labelled but never lit.
 */
export const STAGES = [
  'search',
  'download',
  'ocr',
  'abstract_screening',
  'full_text_screening',
  'extraction',
  'signal_score',
  'reporting',
] as const
export type Stage = (typeof STAGES)[number]

/**
 * `full_text_screening` → `Full-text screening`; `ocr` → `OCR`.
 *
 * NOT a claim about where a run stopped. `PipelineRun.current_stage` is the
 * last stage the engine *dispatched*, and `DAG.reset_from_node()`
 * (`tasks/orchestrator/dag/engine.py:526`) rewrites it to the re-triggered
 * step, so a run that finished everything and then had one step re-run carries
 * an early stage name while being entirely complete. Label it, do not diagnose
 * from it.
 */
const STAGE_LABELS: Record<string, string> = {
  ocr: 'OCR',
  full_text_screening: 'Full-text screening',
  abstract_screening: 'Abstract screening',
  signal_score: 'Signal score',
  deep_research: 'Deep research',
}

export function stageLabel(stage: string): string {
  const known = STAGE_LABELS[stage]
  if (known) return known
  const words = stage.replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

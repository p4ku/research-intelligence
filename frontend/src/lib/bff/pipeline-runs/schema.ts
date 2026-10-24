/**
 * OUR pipeline-run contract: the slice of a run the UI needs (funnel counters,
 * dates, status line). Django's current serializer is richer; the requested
 * endpoint may simply paginate the existing shape — the BFF trims it. Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'

export const runStatus = z
  .enum(['pending', 'running', 'paused', 'completed', 'failed', 'aborted'])
  .meta({ id: 'PipelineRunStatus' })
export type RunStatus = z.infer<typeof runStatus>

export const pipelineRun = z
  .object({
    id: z.uuid(),
    workspace_id: z.uuid(),
    /** The domain the run belongs to — its workspace's name, as Django sends it. */
    workspace_name: z.string(),
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
    /** The search window's first day (YYYY-MM-DD); null when the run was given none. */
    period_start: z.iso.date().nullable(),
    /** The search window's last day (YYYY-MM-DD); null when the run was given none. */
    period_end: z.iso.date().nullable(),
    /** The relative window ("last N days") for runs started without dates. */
    lookback_days: z.number().int().nullable(),
    /**
     * Whether a start with the same domain and window is the same job: false
     * when the run carried options (a limit, a query prefix) that only the
     * MCP tools set, so Home offers no Retry for it.
     */
    retryable: z.boolean(),
  })
  .meta({ id: 'PipelineRun' })
export type PipelineRun = z.infer<typeof pipelineRun>

/**
 * What Home sends to start a briefing: the domain and the search window.
 * Dates are calendar days; the end may not precede the start. Both optional
 * so a Retry can resend exactly what the failed run had, including nothing.
 */
export const startRun = z
  .object({
    workspace_id: z.uuid(),
    start_date: z.iso.date().optional(),
    end_date: z.iso.date().optional(),
    /** A relative window ("last N days") instead of dates — what a Retry resends. */
    lookback_days: z.number().int().positive().optional(),
    run_type: z.enum(['intelligence', 'slr']).optional(),
  })
  .refine((v) => !v.start_date || !v.end_date || v.start_date <= v.end_date, {
    message: 'The end date must not be before the start date.',
    path: ['end_date'],
  })
  .meta({ id: 'StartPipelineRun' })
export type StartRun = z.infer<typeof startRun>

/** The run that was started; the list carries everything else. */
export const startedRun = z.object({ run_id: z.uuid() }).meta({ id: 'StartedPipelineRun' })
export type StartedRun = z.infer<typeof startedRun>

/** The run that was stopped; the list carries everything else. */
export const abortedRun = z
  .object({ run_id: z.uuid(), status: z.literal('aborted') })
  .meta({ id: 'AbortedPipelineRun' })
export type AbortedRun = z.infer<typeof abortedRun>

export const runsQuery = listQuery.extend({
  /** Absent = every domain the user belongs to. */
  workspace_id: z.uuid().optional(),
  status: runStatus.optional(),
})
export type RunsQuery = z.infer<typeof runsQuery>

export const runPage = pageSchema(pipelineRun).meta({ id: 'PipelineRunPage' })

/**
 * One run in full: the list shape plus what it produced, what it cost and
 * where its artefacts landed. Backs `/runs/[id]`.
 */
export const pipelineRunDetail = pipelineRun
  .extend({
    /** Username, or null for a scheduled/system run. */
    triggered_by: z.string().nullable(),
    reprocess_existing: z.boolean(),
    tokens_in: z.number().int(),
    tokens_out: z.number().int(),
    total_tokens: z.number().int(),
    papers_count: z.number().int(),
    duplicates_count: z.number().int(),
    extractions_count: z.number().int(),
    storage: z.object({ size_formatted: z.string(), files: z.number().int() }).nullable(),
  })
  .meta({ id: 'PipelineRunDetail' })
export type PipelineRunDetail = z.infer<typeof pipelineRunDetail>

/**
 * `full_text_screening` → `Full-text screening`; `ocr` → `OCR`.
 *
 * NOT a claim about where a run stopped. `PipelineRun.current_stage` is the
 * last stage the engine *dispatched*, and `DAG.reset_from_node()`
 * (`tasks/orchestrator/dag/engine.py:526`) rewrites it to the re-triggered
 * step, so a run that finished everything and then had one step re-run carries
 * an early stage name while being entirely complete. Label it, do not diagnose
 * from it.
 *
 * The labels are English *source strings*, not display strings: this is the
 * wire-shaped layer and stays language-free. Callers render `t(stageLabel(s))`
 * and the German lives in `src/locales/de/runs.ts` under these exact keys.
 */
/**
 * The English name of each known stage — frontend copy, rendered through
 * `t(stageLabel(stage))`. Exported so `runs/run-presentation.test.ts` can
 * check the dictionary covers it; the call site is dynamic, so the static
 * i18n audit cannot.
 */
export const STAGE_LABELS: Record<string, string> = {
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

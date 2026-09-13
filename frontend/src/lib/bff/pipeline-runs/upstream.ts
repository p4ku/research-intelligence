/**
 * zod transcription of `PipelineRunSerializer` as it exists today. `.loose()`:
 * extra fields pass; missing/mistyped fields fail as 502 `upstream-shape`.
 * Pure — the conformance script imports this.
 */
import * as z from 'zod'

export const pipelineRunDTO = z.looseObject({
  id: z.string(),
  workspace: z.string(),
  workspace_name: z.string(),
  /** YYYY-MM-DD (the trigger date). */
  run_date: z.string(),
  status: z.string(),
  current_stage: z.string().nullable(),
  total_papers_fetched: z.number(),
  total_papers_passed_screening: z.number(),
  tokens_in: z.number(),
  tokens_out: z.number(),
  tokens_consumed: z.number(),
  /** DRF Decimal → string. */
  usd_cost: z.string(),
  triggered_by: z.number().nullable(),
  triggered_by_username: z.string().nullable(),
  reprocess_existing: z.boolean(),
  status_message: z.string().nullable(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  /** Pre-formatted with an emoji; prefer duration_seconds. */
  execution_time_display: z.string(),
  /**
   * The engine's inputs, written at creation: the search window as
   * `start_date`/`end_date` (ISO strings) or `n_last_days`. Absent from
   * captures taken before the serializer exposed it, hence optional.
   */
  configuration_override: z
    .looseObject({
      start_date: z.string().nullish(),
      end_date: z.string().nullish(),
      n_last_days: z.number().nullish(),
      /** Options only the MCP tools set; Home's form cannot reproduce them. */
      limit: z.number().nullish(),
      query_prefix: z.string().nullish(),
    })
    .nullish(),
  /** Django's own rendering of the window ("2026-08-01 - 2026-09-05"); the BFF reads the raw dates instead. */
  period: z.string().nullish(),
})

/**
 * `POST /api/pipeline-runs/start/` — the autonomous-run trigger answers with
 * a status envelope, not the run serializer. Only the id matters to the UI;
 * the page re-reads the list for the row.
 */
/** What the BFF sends Django to start a run. */
export const startRunRequestDTO = z.object({
  workspace_id: z.string(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  n_last_days: z.number().nullable(),
  autonomous: z.literal(true),
})

export const startRunResponseDTO = z.looseObject({
  status: z.string().optional(),
  pipeline_run_id: z.string(),
})

/**
 * `POST /api/pipeline-runs/{id}/abort/` — the same kind of envelope. Refusals
 * do not reach this schema: they are 400s with an `error` sentence, mapped
 * by abort.ts.
 */
export const abortRunResponseDTO = z.looseObject({
  success: z.boolean().optional(),
  status: z.string().optional(),
  message: z.string().optional(),
  pipeline_run_id: z.string(),
})

/**
 * `PipelineRunDetailSerializer` — the list shape plus per-run counts and
 * storage stats. `storage_stats` is loose because the serializer's success
 * path returns `size_bytes` while its exception fallback returns
 * `total_bytes`; the service reads whichever is present.
 */
export const pipelineRunDetailDTO = pipelineRunDTO.extend({
  papers_count: z.number(),
  duplicates_count: z.number(),
  extractions_count: z.number(),
  storage_stats: z.looseObject({ size_formatted: z.string() }).nullable(),
})

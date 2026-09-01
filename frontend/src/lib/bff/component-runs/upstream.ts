/**
 * zod transcription of `ComponentRunSerializer` as it exists today. `.loose()`:
 * extra fields pass; missing/mistyped fields fail as 502 `upstream-shape`.
 *
 * `metrics`, `input_params` and `output_data` stay `unknown` on purpose — they
 * are engine-authored JSON with no stable schema, and `service.ts` is the one
 * place allowed to read keys out of them. Pure — the conformance script
 * imports this.
 */
import * as z from 'zod'

export const componentRunDTO = z.looseObject({
  id: z.string(),
  pipeline_run: z.string(),
  step_type: z.string(),
  component_name: z.string(),
  status: z.string(),
  celery_task_id: z.string().nullable(),
  raw_storage_path: z.string().nullable(),
  input_params: z.unknown(),
  metrics: z.unknown(),
  output_data: z.unknown(),
  error_message: z.string().nullable(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  /** Pre-formatted (`43.0s`, `1m 08s`); the UI formats from duration_seconds. */
  execution_time_display: z.string(),
})

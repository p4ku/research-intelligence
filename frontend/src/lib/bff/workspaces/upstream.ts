/**
 * zod transcription of the Django serializers this resource depends on
 * *today* (`backend/api/serializers/workspaces.py`). `.loose()`: Django may
 * add fields freely; missing/mistyped fields fail as 502 `upstream-shape`.
 * Pure — the conformance script imports this.
 */
import * as z from 'zod'

export const extractionDefinitionDTO = z.looseObject({
  id: z.string(),
  name: z.string(),
  system_prompt: z.string(),
  user_prompt_template: z.string(),
  response_schema: z.record(z.string(), z.unknown()),
  exit_metrics: z.array(z.string()).optional(),
  primary_frontend_metric: z.string().nullable().optional(),
  secondary_frontend_metrics: z.array(z.string()).optional(),
  has_postprocessing_code: z.boolean().optional(),
  postprocessing_code: z.string().optional(),
  llm_model: z.string(),
  version: z.number().optional(),
  requires_consensus: z.boolean().optional(),
  is_active: z.boolean(),
  created_at: z.string(),
})

export const scraperDTO = z.looseObject({
  id: z.string(),
  workspace: z.string(),
  provider: z.string(),
  search_query: z.string(),
  limit: z.number(),
  sort_by: z.string(),
  sort_order: z.string(),
  n_last_days: z.number().nullable().optional(),
  is_active: z.boolean(),
  created_at: z.string(),
})

export const subscriberDTO = z.looseObject({
  id: z.string(),
  email: z.string(),
  name: z.string().nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
})

export const workspaceDTO = z.looseObject({
  id: z.string(),
  name: z.string(),
  scrapers: z.array(scraperDTO),
  abstract_acceptance_criteria: z.string(),
  abstract_rejection_criteria: z.string(),
  abstract_screening_system_prompt: z.string().nullable().optional(),
  abstract_screening_user_prompt_template: z.string().nullable().optional(),
  abstract_screening_response_schema: z.record(z.string(), z.unknown()).nullable().optional(),
  abstract_screening_exit_metric: z.string().nullable().optional(),
  full_text_acceptance_criteria: z.string(),
  full_text_rejection_criteria: z.string(),
  full_text_screening_system_prompt: z.string().nullable().optional(),
  full_text_screening_user_prompt_template: z.string().nullable().optional(),
  full_text_screening_response_schema: z.record(z.string(), z.unknown()).nullable().optional(),
  full_text_screening_exit_metric: z.string().nullable().optional(),
  signal_score_code: z.string().nullable().optional(),
  skip_abstract_screening: z.boolean().optional(),
  reprocess_existing: z.boolean().optional(),
  reasoning_effort: z.string().optional(),
  extraction_definitions: z.array(extractionDefinitionDTO),
  ocr_provider: z.string().nullable(),
  screening_llm_model: z.string(),
  llm_provider: z.string(),
  /** Legacy field; the backend now always sends null (serializer shim since f3942c4). */
  digest_schedule: z.string().nullable(),
  monthly_token_limit: z.number(),
  tokens_in_consumed_this_month: z.number(),
  tokens_out_consumed_this_month: z.number(),
  tokens_consumed_this_month: z.number(),
  /** DRF Decimals serialize as strings. */
  monthly_usd_limit: z.string(),
  usd_spent_this_month: z.string(),
  subscribers: z.array(subscriberDTO),
  /** The caller's role; 'admin' for superusers; null for non-members. */
  user_role: z.string().nullable(),
  created_at: z.string(),
})

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
  llm_model: z.string(),
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
  full_text_acceptance_criteria: z.string(),
  full_text_rejection_criteria: z.string(),
  extraction_definitions: z.array(extractionDefinitionDTO),
  ocr_provider: z.string().nullable(),
  screening_llm_model: z.string(),
  llm_provider: z.string(),
  digest_schedule: z.string().nullable().optional(),
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

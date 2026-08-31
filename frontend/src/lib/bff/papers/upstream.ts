/**
 * zod transcription of the Django serializers this resource depends on
 * *today* (`backend/api/serializers/papers.py`, `extractions.py`). `.loose()`:
 * extra fields pass; missing/mistyped fields fail as 502 `upstream-shape`.
 * Pure — the conformance script imports this.
 */
import * as z from 'zod'
import { scoreVariableValue } from './schema'

/** `signal_score_details` on PaperMetric — `{}` until the scorer has run. */
export const signalScoreDetailsDTO = z.looseObject({
  variables: z.record(z.string(), scoreVariableValue).optional(),
  code_snippet: z.string().optional(),
  score: z.number().optional(),
  calculated_at: z.string().optional(),
  error: z.string().nullable().optional(),
})

/** PaperMetricSerializer (fields='__all__'); one row per (paper, pipeline_run). */
export const paperMetricDTO = z.looseObject({
  id: z.string(),
  paper: z.string(),
  pipeline_run: z.string().nullable(),
  workspace: z.string(),
  signal_score: z.number().nullable(),
  signal_score_details: signalScoreDetailsDTO,
  /** Sanitized definition name → value; pre-filled with 0.0 for every definition. */
  metrics_data: z.record(z.string(), z.unknown()),
  created_at: z.string(),
})

/** PaperSerializer — note: no `signal_score`; it lives on the nested metrics[]. */
export const paperDTO = z.looseObject({
  id: z.string(),
  workspace: z.string(),
  pipeline_run: z.string(),
  hash_id: z.string(),
  doi: z.string().nullable(),
  arxiv_id: z.string().nullable(),
  title: z.string(),
  /** Comma-joined at ingest ("A. Author, B. Author"). */
  authors: z.string(),
  abstract: z.string(),
  source_database: z.string(),
  original_pdf_path: z.string().nullable(),
  converted_md_path: z.string().nullable(),
  /** Includes 'accepted', which the model's choices omit — keep it open. */
  screening_status: z.string(),
  screening_reasoning: z.string().nullable(),
  is_evaluation_benchmark: z.boolean(),
  evaluation_label: z.enum(['passed', 'rejected']).nullable(),
  metrics: z.array(paperMetricDTO),
  created_at: z.string(),
})

/** ExtractionSerializer (fields='__all__'). `fields_data` is flat or `{fields:{…}}`. */
export const extractionDTO = z.looseObject({
  id: z.string(),
  workspace: z.string(),
  paper: z.string(),
  /** null when the definition was deleted (SET_NULL). */
  extraction_definition: z.string().nullable(),
  /** Equals the definition's name at write time. */
  category: z.string(),
  fields_data: z.record(z.string(), z.unknown()).nullable(),
  is_hitl_validated: z.boolean(),
  version_info: z.record(z.string(), z.unknown()),
  validation_status: z.string(),
  review_required: z.boolean(),
  confidence_score: z.number().nullable(),
  confidence_method: z.string().nullable(),
  created_at: z.string(),
})

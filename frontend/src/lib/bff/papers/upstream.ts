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
  /**
   * What this run decided about the paper. Optional: the model has carried
   * them since 28 Aug 2026, but a deployment whose serializer predates that
   * omits them — the paper-level (latest-run) values stand in then.
   */
  screening_status: z.string().optional(),
  abstract_screening_reasoning: z.string().nullable().optional(),
  full_text_screening_reasoning: z.string().nullable().optional(),
  created_at: z.string(),
})

/** PaperSerializer — note: no `signal_score`; it lives on the nested metrics[]. */
export const paperDTO = z.looseObject({
  id: z.string(),
  workspace: z.string(),
  pipeline_run: z.string().nullable(),
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
  /**
   * `Paper.source_url` — the backend's one public link for the paper (arXiv
   * abstract page, DOI, or the provider's landing page). Optional only so
   * replays captured before the column existed still parse.
   */
  source_url: z.string().nullable().optional(),
  /** Includes 'accepted', which the model's choices omit — keep it open. */
  screening_status: z.string(),
  screening_reasoning: z.string().nullable(),
  /**
   * The two stages' reasons and the source's publication date, on the paper
   * since 8 Sep 2026. Optional so earlier replays still parse; the metric row
   * carries the same two reasons for a run.
   */
  abstract_screening_reasoning: z.string().nullable().optional(),
  full_text_screening_reasoning: z.string().nullable().optional(),
  published_date: z.string().nullable().optional(),
  pipeline_run_name: z.string().nullable().optional(),
  is_evaluation_benchmark: z.boolean(),
  evaluation_label: z.enum(['passed', 'rejected']).nullable(),
  signal_score: z.number().nullable().optional(),
  signal_score_details: signalScoreDetailsDTO.optional(),
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
  /**
   * The model's `exit_metric` property, serialised as a string ("63.6").
   * Optional: older replays predate it. When present it names the headline
   * value outright, which is tier 1 of the resolution the mapper otherwise
   * approximates from the definition's name.
   */
  exit_metric: z.string().nullable().optional(),
  created_at: z.string(),
})

/**
 * Paper schema for briefing editions.
 * Represents a scored paper within a briefing edition, with resilient default values
 * so that both lightweight summary payloads and full scorecard payloads parse cleanly.
 */
import * as z from 'zod'
import {
  dimension,
  riskAndAffiliation,
  screeningStatus,
  signalScoreDetails,
} from '../papers/schema'

export const editionPaper = z
  .object({
    id: z.string(),
    workspace_id: z.string().default(''),
    pipeline_run_id: z.string().default(''),
    title: z.string(),
    authors: z.array(z.string()).default([]),
    authors_raw: z.string().default(''),
    abstract: z.string().default(''),
    doi: z.string().nullable().default(null),
    arxiv_id: z.string().nullable().default(null),
    source: z.string().default('arXiv'),
    screening_status: screeningStatus.default('accepted'),
    screening_reasoning: z.string().nullable().default(null),
    abstract_screening_reasoning: z.string().nullable().default(null),
    full_text_screening_reasoning: z.string().nullable().default(null),
    signal_score: z.number().nullable().default(null),
    signal_score_details: signalScoreDetails.nullable().default(null),
    dimensions: z.array(dimension).default([]),
    pdf_key: z.string().nullable().default(null),
    markdown_key: z.string().nullable().default(null),
    source_url: z.string().nullable().default(null),
    is_benchmark: z.boolean().default(false),
    evaluation_label: z.string().nullable().optional().default(null),
    published_date: z.string().nullable().default(null),
    created_at: z.string().default(''),
    pipeline_run_name: z.string().nullable().default(null),
    risk_and_affiliation: riskAndAffiliation.nullable().optional(),
  })
  .passthrough()
  .meta({ id: 'EditionPaper' })

export type EditionPaper = z.infer<typeof editionPaper>

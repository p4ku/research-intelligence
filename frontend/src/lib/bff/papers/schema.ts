/**
 * OUR papers contract: `ScoredPaper` — a paper with its composite signal
 * score and every dimension resolved against the workspace's extraction
 * definitions. This is the shape the UI renders *and* the shape we ask
 * Django to serve from a workspace-scoped, paginated scorecard endpoint.
 * Until then the BFF composes it (see ./compose.ts, port reference
 * src/lib/papers/map.ts). Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'

export const screeningStatus = z
  .enum([
    'pending',
    'abstract_passed',
    'full_text_passed',
    'accepted',
    'borderline',
    'rejected',
    'withdrawn',
  ])
  .meta({ id: 'ScreeningStatus' })
export type ScreeningStatus = z.infer<typeof screeningStatus>

export const SCREENING_STATUSES: ScreeningStatus[] = [...screeningStatus.options]

/** Statuses that count as "through screening". */
export const PASSED_STATUSES: ScreeningStatus[] = [
  'abstract_passed',
  'full_text_passed',
  'accepted',
]

export const dimension = z
  .object({
    /** Sanitized definition name; also the key in signal-score variables. */
    key: z.string(),
    /** null when the definition was deleted (name comes from the extraction's category). */
    definition_id: z.uuid().nullable(),
    /** Rendered verbatim — never translated. */
    name: z.string(),
    /** Parsed numeric value; null when there is no extraction or it isn't numeric. */
    value: z.number().nullable(),
    /** Display string as the backend would show it ('—' when no extraction). */
    raw: z.string(),
    /** Scale for bars/radar; null → show the number only. */
    max: z.number().nullable(),
    is_trl: z.boolean(),
    rationale: z.string().optional(),
    evidence: z.array(z.string()).optional(),
    confidence: z.number().nullable().optional(),
    validation_status: z.string().optional(),
    review_required: z.boolean().optional(),
    extraction_id: z.uuid().optional(),
  })
  .meta({ id: 'Dimension' })
export type Dimension = z.infer<typeof dimension>

/**
 * A value the scoring formula saw. Extraction output is whatever the LLM
 * produced for that dimension — production has booleans (e.g.
 * `limitations_acknowledged`) alongside numbers and strings, and a null is
 * possible when an extraction is missing.
 */
export const scoreVariableValue = z.union([z.number(), z.string(), z.boolean(), z.null()])
export type ScoreVariableValue = z.infer<typeof scoreVariableValue>

export const signalScoreDetails = z
  .object({
    /** Dimension key → the value the formula saw. */
    variables: z.record(z.string(), scoreVariableValue),
    /** The workspace's scoring snippet as evaluated for this paper. */
    code_snippet: z.string().nullable(),
    calculated_at: z.string().nullable(),
    /** Set when the formula failed for this paper. */
    error: z.string().nullable(),
  })
  .meta({ id: 'SignalScoreDetails' })
export type SignalScoreDetails = z.infer<typeof signalScoreDetails>

export const scoredPaper = z
  .object({
    id: z.uuid(),
    workspace_id: z.uuid(),
    pipeline_run_id: z.uuid(),
    title: z.string(),
    authors: z.array(z.string()),
    authors_raw: z.string(),
    abstract: z.string(),
    doi: z.string().nullable(),
    arxiv_id: z.string().nullable(),
    /** 'arxiv' | 'openalex' | 'lens' | … */
    source: z.string(),
    screening_status: screeningStatus,
    screening_reasoning: z.string().nullable(),
    signal_score: z.number().nullable(),
    signal_score_details: signalScoreDetails.nullable(),
    /** Workspace definition order; definition-less extractions appended. */
    dimensions: z.array(dimension),
    /** Storage keys — there is no file endpoint yet. */
    pdf_key: z.string().nullable(),
    markdown_key: z.string().nullable(),
    /** External link (arXiv / DOI) when the ids allow one. */
    pdf_url: z.string().nullable(),
    is_benchmark: z.boolean(),
    evaluation_label: z.enum(['passed', 'rejected']).nullable(),
    /** Ingest time (ISO 8601). The backend stores no publication date. */
    created_at: z.iso.datetime({ offset: true }),
  })
  .meta({ id: 'ScoredPaper' })
export type ScoredPaper = z.infer<typeof scoredPaper>

export const papersQuery = listQuery.extend({
  /** Absent = every domain the user belongs to. */
  workspace_id: z.uuid().optional(),
  /** 'passed' = the three passed statuses; 'all' = everything. */
  screening: z
    .enum([
      'passed',
      'all',
      'pending',
      'abstract_passed',
      'full_text_passed',
      'accepted',
      'borderline',
      'rejected',
      'withdrawn',
    ])
    .default('all'),
  /** `signal_score` | `created_at` | `dim:<key>`, `-` prefix for descending. */
  ordering: z
    .string()
    .regex(/^-?(signal_score|created_at|dim:[a-z0-9_]+)$/)
    .default('-signal_score'),
  /** Free text over title, abstract, authors, arxiv id, doi — the shared matcher in src/lib/search/match.ts. */
  search: z.string().optional(),
})
export type PapersQuery = z.infer<typeof papersQuery>

export const paperPage = pageSchema(scoredPaper).meta({ id: 'ScoredPaperPage' })

/**
 * A paper as the Ask picker names it: the slim projection a console holds
 * for every paper the user can see, so the corpus travels in kilobytes.
 */
export const paletteEntry = z
  .object({
    id: z.uuid(),
    title: z.string(),
    first_author: z.string().nullable(),
    source: z.string(),
    signal_score: z.number().nullable(),
    created_at: z.iso.datetime({ offset: true }),
  })
  .meta({ id: 'PaletteEntry' })
export type PaletteEntry = z.infer<typeof paletteEntry>

/** Best signal first, unscored papers last. */
export const palette = z.object({ papers: z.array(paletteEntry) }).meta({ id: 'Palette' })
export type Palette = z.infer<typeof palette>

/**
 * The picker's one automatic retry announces itself, so a failed first load
 * can be traced from the router's access log alone: `retry=1` marks the
 * second request, `after` names the problem the first one ended in. A
 * marker only, read leniently: a malformed one is ignored, never a 400.
 */
export const paletteQuery = z.object({
  retry: z.literal('1').optional(),
  /** A problem slug, nothing else — this value is written to the log. */
  after: z
    .string()
    .regex(/^[a-z0-9-]{1,64}$/)
    .optional(),
})

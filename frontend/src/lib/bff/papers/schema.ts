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

/**
 * A sub-score a definition emits beside its headline: `need_match_score` →
 * "Need match", with a `need_match_assessment` twin, when there is one, as
 * `text`. Names are humanised from the key and never translated — they are
 * the definition's own vocabulary, like its name.
 */
export const dimensionFacet = z
  .object({
    key: z.string(),
    name: z.string(),
    value: z.number(),
    /** The definition's scale; null → show the figure only (a TRL definition's sub-scores declare no range). */
    max: z.number().nullable(),
    text: z.string().nullable(),
  })
  .meta({ id: 'DimensionFacet' })
export type DimensionFacet = z.infer<typeof dimensionFacet>

/** A labelled string field of a definition's payload (a longer prose field, or a short fact). */
export const dimensionField = z
  .object({ key: z.string(), name: z.string(), value: z.union([z.string(), z.boolean()]) })
  .meta({ id: 'DimensionField' })
export type DimensionField = z.infer<typeof dimensionField>

/** A labelled string list of a definition's payload ("Key contributions", "Evidence gaps"). */
export const dimensionList = z
  .object({ key: z.string(), name: z.string(), items: z.array(z.string()) })
  .meta({ id: 'DimensionList' })
export type DimensionList = z.infer<typeof dimensionList>

export const riskFlag = z
  .object({
    key: z.string(),
    label: z.string(),
    value: z.string(),
    status: z.string(),
  })
  .meta({ id: 'RiskFlag' })
export type RiskFlag = z.infer<typeof riskFlag>

export const riskAndAffiliation = z
  .object({
    raw: z.record(z.string(), z.any()).optional(),
    affiliations: z.array(z.string()).default([]),
    author_contacts: z.array(z.string()).default([]),
    funding_entities: z.array(z.string()).default([]),
    codebase_artifact_link: z.string().nullable().optional(),
    schwarz_ecosystem_affiliation: z.string().nullable().optional(),
    gdpr_concerns: z.string().nullable().optional(),
    competitor_involvement: z.string().nullable().optional(),
    risk_score: z.number().nullable().optional(),
    risk_score_assessment: z.string().nullable().optional(),
    flags: z.array(riskFlag).default([]),
  })
  .meta({ id: 'RiskAndAffiliation' })
export type RiskAndAffiliation = z.infer<typeof riskAndAffiliation>

export const dimension = z
  .object({
    /** Sanitized definition name; also the key in signal-score variables. */
    key: z.string(),
    /** null when the definition was deleted (name comes from the extraction's category). */
    definition_id: z.uuid().nullable(),
    /** Rendered verbatim — never translated. */
    name: z.string(),
    label: z.string().optional(),
    /** Parsed numeric value; null when there is no extraction or it isn't numeric. */
    value: z.number().nullable(),
    /** Display string as the backend would show it ('—' when no extraction). */
    raw: z.string(),
    /** Scale for bars/radar; null → show the number only. */
    max: z.number().nullable(),
    is_trl: z.boolean(),
    is_risk_and_affiliation: z.boolean().optional(),
    has_postprocessing: z.boolean().optional(),
    primary_metric: z.record(z.string(), z.any()).optional(),
    secondary_metrics: z.array(z.record(z.string(), z.any())).optional(),
    main_metric: z.record(z.string(), z.any()).optional(),
    auxiliary_metrics: z.array(z.record(z.string(), z.any())).optional(),
    is_hitl: z.boolean().optional(),
    fields_data: z.record(z.string(), z.any()).nullable().optional(),
    response_schema: z.record(z.string(), z.any()).nullable().optional(),
    exit_metrics: z.array(z.string()).optional(),
    rationale: z.string().optional(),
    evidence: z.array(z.string()).optional(),
    confidence: z.number().nullable().optional(),
    validation_status: z.string().optional(),
    review_required: z.boolean().optional(),
    extraction_id: z.uuid().optional(),
    /**
     * What else the definition emitted, shaped by the payload alone so a new
     * definition renders without a frontend change: its band label when it
     * has one ("Sound", "Technology validated in lab"), its sub-scores, its
     * longer prose fields, its lists, its short facts, and the model that
     * wrote them. All in payload order; `*_computed` / `*_postprocessed`
     * duplicates are dropped.
     */
    band: z.string().optional(),
    facets: z.array(dimensionFacet).optional(),
    texts: z.array(dimensionField).optional(),
    lists: z.array(dimensionList).optional(),
    facts: z.array(dimensionField).optional(),
    model: z.string().nullable().optional(),
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
    /** The two stages' reasons when the run recorded them apart; `screening_reasoning` stands in otherwise. */
    abstract_screening_reasoning: z.string().nullable(),
    full_text_screening_reasoning: z.string().nullable(),
    signal_score: z.number().nullable(),
    signal_score_details: signalScoreDetails.nullable(),
    /** Workspace definition order; definition-less extractions appended. */
    dimensions: z.array(dimension),
    /** Storage keys — there is no file endpoint yet. */
    pdf_key: z.string().nullable(),
    markdown_key: z.string().nullable(),
    /**
     * The one public link for the paper, verbatim from `Paper.source_url`:
     * arXiv abstract page, DOI, or the provider's landing page. Never rebuilt
     * from `arxiv_id` / `doi` here — the backend owns that rule.
     */
    source_url: z.string().nullable(),
    is_benchmark: z.boolean(),
    evaluation_label: z.enum(['passed', 'rejected']).nullable(),
    /** The source's publication date (ISO 8601 date), when the backend has it. */
    published_date: z.string().nullable(),
    /** Ingest time (ISO 8601). */
    created_at: z.iso.datetime({ offset: true }),
    /** The scoring run's display name, beside its id. */
    pipeline_run_name: z.string().nullable(),
    risk_and_affiliation: riskAndAffiliation.nullable().optional(),
  })
  .meta({ id: 'ScoredPaper' })
export type ScoredPaper = z.infer<typeof scoredPaper>

/** What the scorecard endpoint is asked for — the part of the query Django is meant to absorb. */
export const papersScorecardQuery = listQuery.extend({
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
  search: z.string().trim().max(200).optional(),
})

/**
 * The BFF face: the Papers page's every control on top of the scorecard
 * query, so the browser holds one page and the corpus stays on the server.
 * Unusable values fall to their defaults rather than failing the page.
 */
export const papersQuery = papersScorecardQuery.extend({
  /** Absent = every domain the user belongs to. */
  workspace_id: z.uuid().optional(),
  /** '1' = only the reader's starred papers. */
  starred: z.enum(['0', '1']).catch('0').default('0'),
  /** Papers scoring at least this; 0 = no cutoff. */
  min_score: z.coerce.number().min(0).catch(0).default(0),
  /** TRL window, applied only when the corpus has a TRL dimension. */
  min_trl: z.coerce.number().int().min(1).max(9).catch(1).default(1),
  max_trl: z.coerce.number().int().min(1).max(9).catch(9).default(9),
  /** Ingested within this many days of the newest paper; 0 = all time. */
  within_days: z.coerce.number().int().min(0).max(3650).catch(0).default(0),
})
export type PapersQuery = z.infer<typeof papersQuery>

export const paperPage = pageSchema(scoredPaper).meta({ id: 'ScoredPaperPage' })

/**
 * What the filter rail needs from the whole corpus, however narrow the page:
 * the sort options and slider ceiling exist only if some paper has the
 * value, and the counts say what a filter is hiding.
 */
export const papersFacets = z
  .object({
    /** Papers in the corpus before any filter. */
    total: z.number().int().min(0),
    /** The score slider's top: 100, or higher when a formula scores higher. */
    score_ceiling: z.number().int(),
    /** The newest ingest time — what the ingested window counts back from. */
    newest: z.iso.datetime({ offset: true }).nullable(),
    has_trl: z.boolean(),
    /** Definitions some paper has a value for, once each across domains; TRL excluded. */
    dimension_sorts: z.array(z.object({ key: z.string(), name: z.string() })),
    starred_count: z.number().int().min(0),
    /** Search hits the screening filter alone is hiding (0 without a search). */
    hidden_by_screening: z.number().int().min(0),
    /** Set when the per-user corpus cap dropped older papers. */
    truncated: z.object({ shown: z.number().int(), total: z.number().int() }).nullable(),
  })
  .meta({ id: 'PapersFacets' })
export type PapersFacets = z.infer<typeof papersFacets>

export const paperList = pageSchema(scoredPaper)
  .extend({ facets: papersFacets })
  .meta({ id: 'ScoredPaperList' })
export type PapersList = z.infer<typeof paperList>

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

/**
 * What the picker asks for: the reader's text (empty warms the corpus and
 * returns the top rows by signal) through the shared matcher, at most
 * `limit` rows. Never the whole corpus — the picker is a typeahead.
 */
export const paletteQuery = z.object({
  q: z.string().trim().max(200).default(''),
  limit: z.coerce.number().int().min(1).max(50).catch(20).default(20),
})
export type PaletteQuery = z.infer<typeof paletteQuery>

/** Best signal first for an empty query, best match first otherwise; unscored papers last. */
export const palette = z
  .object({
    query: z.string(),
    papers: z.array(paletteEntry),
    /** Rows the query matched before the limit. */
    matched: z.number().int().min(0),
    /** Papers the reader can see at all. */
    total: z.number().int().min(0),
  })
  .meta({ id: 'Palette' })
export type Palette = z.infer<typeof palette>

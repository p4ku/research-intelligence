/**
 * OUR briefing contract: one edition per completed pipeline run — funnel,
 * the surfaced papers, the screening log (exclusions with reasoning), and a
 * short prose brief. Everything except the prose exists in Django today; the
 * requested endpoint owns the prose (and may simply serialize this shape).
 * Editions are addressed by date within a workspace (same-day reruns resolve
 * to the latest run; `run_id` disambiguates). Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'
import { screeningStatus } from '../papers/schema'

export const editionPaper = z
  .object({
    id: z.uuid(),
    title: z.string(),
    authors: z.array(z.string()),
    source: z.string(),
    /**
     * The run's decision and score for the paper — frozen with the edition,
     * whatever a later run decided. The status is optional until the Django
     * editions endpoint serves it; the UI shows the paper's current one then.
     */
    screening_status: screeningStatus.optional(),
    signal_score: z.number().nullable(),
  })
  .meta({ id: 'EditionPaper' })
export type EditionPaper = z.infer<typeof editionPaper>

export const editionExclusion = z
  .object({
    paper_id: z.uuid(),
    title: z.string(),
    source: z.string(),
    /** The screening model's reasoning, verbatim. */
    reason: z.string().nullable(),
  })
  .meta({ id: 'EditionExclusion' })
export type EditionExclusion = z.infer<typeof editionExclusion>

export const editionSummary = z
  .object({
    run_id: z.uuid(),
    workspace_id: z.uuid(),
    /** The edition's day (from the run's completion). */
    date: z.iso.date(),
    title: z.string(),
    in_brief: z.string(),
    /** 'model' once the backend writes the prose; 'template' meanwhile. */
    in_brief_source: z.enum(['model', 'template']),
    funnel: z.object({
      fetched: z.number().int(),
      passed_screening: z.number().int(),
      surfaced: z.number().int(),
    }),
    /** Surfaced papers, signal-first. */
    papers: z.array(editionPaper),
    generated_at: z.iso.datetime({ offset: true }).nullable(),
  })
  .meta({ id: 'BriefingEditionSummary' })
export type EditionSummary = z.infer<typeof editionSummary>

export const edition = editionSummary
  .extend({ exclusions: z.array(editionExclusion) })
  .meta({ id: 'BriefingEdition' })
export type Edition = z.infer<typeof edition>

export const editionsQuery = listQuery.extend({
  /** Absent = every domain the user belongs to. */
  workspace_id: z.uuid().optional(),
})
export type EditionsQuery = z.infer<typeof editionsQuery>

export const editionPage = pageSchema(editionSummary).meta({ id: 'BriefingEditionPage' })

/**
 * OUR briefing contract: one edition per completed pipeline run — funnel,
 * the surfaced papers, the screening log (exclusions with reasoning), and a
 * short prose brief. Everything except the prose exists in Django today; the
 * requested endpoint owns the prose (and may simply serialize this shape).
 * Editions are addressed by date within a workspace, plus the run id when a
 * domain ran more than once that day (without it, the day's latest). Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'
import { editionPaper } from '../papers/schema'

export { editionPaper, type EditionPaper } from '../papers/schema'

export const editionExclusion = z
  .object({
    paper_id: z.uuid(),
    title: z.string(),
    source: z.string(),
    /** The screening model's reasoning, verbatim. */
    reason: z.string().nullable(),
    published_date: z.string().nullable().optional(),
    source_url: z.string().nullable().optional(),
  })
  .meta({ id: 'EditionExclusion' })
export type EditionExclusion = z.infer<typeof editionExclusion>

export const editionSummary = z
  .object({
    run_id: z.uuid(),
    workspace_id: z.uuid(),
    workspace_name: z.string().optional(),
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
    total: z.number().int().optional(),
    page: z.number().int().optional(),
    page_size: z.number().int().optional(),
    total_pages: z.number().int().optional(),
    total_papers: z.number().int().optional(),
    total_exclusions: z.number().int().optional(),
    definitions: z
      .array(
        z.object({
          id: z.string().optional(),
          key: z.string(),
          name: z.string(),
          order: z.number().optional(),
          is_trl: z.boolean().optional(),
        }),
      )
      .optional(),
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

export const editionQuery = z.object({
  /** Absent = the day's newest edition across every domain the user belongs to. */
  workspace_id: z.uuid().optional(),
  /** Absent = the day's newest edition; set = that run's, when it ran that day. */
  run_id: z.uuid().optional(),
  scope: z.enum(['all', 'included', 'excluded']).optional(),
  page: z.coerce.number().int().min(1).optional(),
  page_size: z.coerce.number().int().min(1).optional(),
  min_score: z.coerce.number().optional(),
  score: z.coerce.number().optional(),
  sort: z.string().optional(),
  ordering: z.string().optional(),
})
export type EditionQuery = z.infer<typeof editionQuery>

export const editionPage = pageSchema(editionSummary).meta({ id: 'BriefingEditionPage' })

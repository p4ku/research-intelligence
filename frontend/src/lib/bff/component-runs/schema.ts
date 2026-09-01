/**
 * OUR component-run contract: one step of a pipeline run, with its `metrics`
 * blob already resolved into a typed per-step summary.
 *
 * Django's `ComponentRun.metrics` is free-form JSON whose keys vary by step
 * and by engine version (search alone writes `duplicates`, `duplicates_count`,
 * `total_duplicates`, `duplicates_skipped` and `total_duplicates_skipped` for
 * the same number). Resolving that here — once, server-side, against a
 * contract — is what keeps the UI from re-deriving it at every call site the
 * way the Django admin does. Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'

export const componentStatus = z
  .enum(['pending', 'running', 'completed', 'skipped', 'failed', 'aborted'])
  .meta({ id: 'ComponentRunStatus' })
export type ComponentStatus = z.infer<typeof componentStatus>

export const stepType = z
  .enum([
    'search',
    'download',
    'ocr',
    'screening',
    'extraction',
    'signal_score',
    'metrics',
    'deep_research',
    'reporting',
  ])
  .meta({ id: 'ComponentStepType' })
export type StepType = z.infer<typeof stepType>

/**
 * What a step did, resolved per step kind. `kind: 'none'` means the step
 * reported no metrics we recognise — the UI says so rather than inventing a
 * zero, which is the distinction the admin's summary loses.
 */
export const componentSummary = z
  .discriminatedUnion('kind', [
    z.object({
      kind: z.literal('search'),
      created: z.number().int(),
      fetched: z.number().int(),
      duplicates: z.number().int(),
    }),
    z.object({
      kind: z.literal('download'),
      downloaded: z.number().int(),
      cached: z.number().int(),
      failed: z.number().int(),
    }),
    z.object({
      kind: z.literal('ocr'),
      converted: z.number().int(),
      failed: z.number().int(),
    }),
    z.object({
      kind: z.literal('screening'),
      screened: z.number().int(),
      passed: z.number().int(),
      rejected: z.number().int(),
      withdrawn: z.number().int(),
    }),
    z.object({
      kind: z.literal('extraction'),
      created: z.number().int(),
      papers: z.number().int(),
      definitions: z.number().int(),
      failed: z.number().int(),
    }),
    z.object({
      kind: z.literal('signal_score'),
      scored: z.number().int(),
      total: z.number().int(),
      avg: z.number().nullable(),
      max: z.number().nullable(),
    }),
    z.object({
      kind: z.literal('reporting'),
      generated: z.boolean(),
      characters: z.number().int().nullable(),
    }),
    z.object({ kind: z.literal('none') }),
  ])
  .meta({ id: 'ComponentSummary' })
export type ComponentSummary = z.infer<typeof componentSummary>

/**
 * Measured spend only. Every field is null when the step did not record it —
 * the BFF never estimates a cost from token heuristics, because a guess and a
 * measurement must not render identically on a page used to judge spend.
 */
export const componentCost = z
  .object({
    usd: z.number().nullable(),
    tokens_in: z.number().int().nullable(),
    tokens_out: z.number().int().nullable(),
    total_tokens: z.number().int().nullable(),
    model: z.string().nullable(),
  })
  .meta({ id: 'ComponentCost' })
export type ComponentCost = z.infer<typeof componentCost>

export const componentRun = z
  .object({
    id: z.uuid(),
    pipeline_run_id: z.uuid(),
    step_type: stepType,
    /** The concrete implementation, e.g. `abstract_screening`, `arxiv_scraper`. */
    component_name: z.string(),
    /** Reads `Abstract Screening` where `component_name` distinguishes it. */
    label: z.string(),
    status: componentStatus,
    summary: componentSummary,
    cost: componentCost,
    duration_seconds: z.number().nullable(),
    started_at: z.iso.datetime({ offset: true }).nullable(),
    completed_at: z.iso.datetime({ offset: true }).nullable(),
    error_message: z.string().nullable(),
    storage_path: z.string().nullable(),
  })
  .meta({ id: 'ComponentRun' })
export type ComponentRun = z.infer<typeof componentRun>

export const componentRunsQuery = listQuery.extend({
  pipeline_run_id: z.uuid(),
})
export type ComponentRunsQuery = z.infer<typeof componentRunsQuery>

export const componentRunPage = pageSchema(componentRun).meta({ id: 'ComponentRunPage' })

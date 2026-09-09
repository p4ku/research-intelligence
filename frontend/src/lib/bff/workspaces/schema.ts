/**
 * OUR workspace contract — the shape the UI renders and the shape we ask
 * Django to serve (the BFF normalises today's serializer into it meanwhile).
 * Pure; zod is the single source of truth (types, validation, OpenAPI).
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'

export const definitionSummary = z
  .object({
    id: z.uuid(),
    /** Rendered verbatim — never translated. */
    name: z.string(),
    /** Sanitized name; also the key in signal-score variables and metrics_data. */
    key: z.string(),
    is_active: z.boolean(),
    is_trl: z.boolean(),
    /** Inferred scale for bars/radar; null when unknown. */
    max: z.number().nullable(),
    primary_frontend_metric: z.string().nullable().optional(),
    secondary_frontend_metrics: z.array(z.string()).optional(),
  })
  .meta({ id: 'ExtractionDefinitionSummary' })

export const workspaceScraper = z
  .object({
    id: z.uuid(),
    provider: z.string(),
    search_query: z.string(),
    is_active: z.boolean(),
  })
  .meta({ id: 'WorkspaceScraper' })

export const workspace = z
  .object({
    id: z.uuid(),
    name: z.string(),
    /** The calling user's role: 'admin' | 'manager' | 'researcher'; null unknown. */
    user_role: z.string().nullable(),
    definitions: z.array(definitionSummary),
    scrapers: z.array(workspaceScraper),
    /** Cron expression for the digest email; null when none. */
    digest_schedule: z.string().nullable(),
    screening_llm_model: z.string().nullable(),
    llm_provider: z.string().nullable(),
    created_at: z.iso.datetime({ offset: true }),
  })
  .meta({ id: 'Workspace' })

export const workspacesQuery = listQuery
export const workspacePage = pageSchema(workspace).meta({ id: 'WorkspacePage' })

export type DefinitionSummary = z.infer<typeof definitionSummary>
export type WorkspaceSummary = z.infer<typeof workspace>

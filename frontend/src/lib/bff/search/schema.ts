/**
 * The search contract: what the Home typeahead asks for and what it gets
 * back. Not paginated — a typeahead shows at most `limit` rows and the
 * "See all" row hands off to the paginated `/bff/papers?search=`. Pure.
 */
import * as z from 'zod'
import { screeningStatus } from '../papers/schema'

export const searchQuery = z.object({
  /** Free text, an arXiv id / DOI / URL, or a question. Empty is valid: it warms the corpus and returns nothing. */
  q: z.string().trim().max(200).default(''),
  limit: z.coerce.number().int().min(1).max(20).catch(8).default(8),
})
export type SearchQuery = z.infer<typeof searchQuery>

export const searchField = z.enum(['title', 'authors', 'abstract', 'id'])

export const searchHit = z
  .object({
    id: z.uuid(),
    title: z.string(),
    authors: z.array(z.string()),
    first_author: z.string().nullable(),
    signal_score: z.number().nullable(),
    workspace_id: z.uuid(),
    workspace_name: z.string(),
    screening_status: screeningStatus,
    created_at: z.iso.datetime({ offset: true }),
    /** A window of the abstract around the first hit, original text — highlight client-side. */
    snippet: z.string(),
    /** Fields that carried the query, title → authors → abstract → id. */
    matched: z.array(searchField),
    /** Relevance; papers arrive sorted by it. */
    score: z.number(),
  })
  .meta({ id: 'SearchHit' })
export type SearchHit = z.infer<typeof searchHit>

export const searchDomain = z
  .object({
    id: z.uuid(),
    name: z.string(),
    papers_matched: z.number().int().min(0),
    /** Newest edition; null when the domain has no completed run yet. */
    latest_edition: z.object({ date: z.iso.date(), href: z.string() }).nullable(),
  })
  .meta({ id: 'SearchDomain' })
export type SearchDomain = z.infer<typeof searchDomain>

export const searchIntent = z.enum(['empty', 'text', 'id', 'question'])
export type SearchIntent = z.infer<typeof searchIntent>

export const searchResponse = z
  .object({
    query: z.string(),
    intent: searchIntent,
    papers: z.array(searchHit),
    papers_total: z.number().int().min(0),
    /** How many of papers_total sit outside the passed screening set — Papers hides those by default. */
    papers_hidden_by_screening: z.number().int().min(0),
    domains: z.array(searchDomain),
    /** An Ask console scoped to the top hit; null when nothing matched. */
    ask: z.object({ href: z.string(), question: z.string(), paper_id: z.uuid() }).nullable(),
    /** intent 'id': the identifier as understood; `exact` is the corpus paper carrying it. */
    id: z.object({ kind: z.enum(['arxiv', 'doi']), value: z.string(), url: z.url() }).nullable(),
    exact: z.object({ paper_id: z.uuid() }).nullable(),
  })
  .meta({ id: 'SearchResponse' })
export type SearchResponse = z.infer<typeof searchResponse>

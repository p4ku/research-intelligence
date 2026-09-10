/**
 * OUR chat contract: the stream request, the SSE event frames the UI
 * consumes, and sessions/turns for the history rail. Pure.
 *
 * Stream framing (both from `/bff/chat/stream` and requested of Django):
 * `id: <n>\nevent: <name>\ndata: <one-line JSON>\n\n`, with `: ping <iso>`
 * comment heartbeats every 15 s. Event order:
 * `metadata` → `citations`? → `delta`* → `visual_citations`? → `fact_check`?
 * → `usage` → `done`; `error` may replace anything and ends the stream.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'
import { problemSchema } from '../core/problem-schema'

export const chatStreamRequest = z
  .object({
    question: z.string().min(1).max(4000),
    /** Exactly one of workspace_id (corpus scope) or paper_id (one paper). */
    workspace_id: z.uuid().optional(),
    paper_id: z.uuid().optional(),
    /** Continue an existing session; omitted → one is created implicitly. */
    session_id: z.uuid().optional(),
    deep_thinking: z.boolean().default(false),
  })
  .refine((d) => Boolean(d.workspace_id) !== Boolean(d.paper_id), {
    message: 'Provide exactly one of workspace_id or paper_id.',
    path: ['workspace_id'],
  })
  .meta({ id: 'ChatStreamRequest' })
export type ChatStreamRequest = z.infer<typeof chatStreamRequest>

export const paperCitation = z
  .object({
    paper_id: z.uuid(),
    title: z.string(),
    signal_score: z.number().nullable(),
    /** App-relative link, e.g. /papers/<id>. */
    href: z.string(),
  })
  .meta({ id: 'PaperCitation' })
export type PaperCitation = z.infer<typeof paperCitation>

/** A page/figure/quote reference inside the session's paper (Gemini boxes 0–1000). */
export const visualCitation = z
  .object({
    page: z.number().int().nullish(),
    label: z.string().nullish(),
    box_2d: z.array(z.number()).length(4).nullish(),
    quote: z.string().nullish(),
    verified_in_source: z.boolean().nullish(),
  })
  .meta({ id: 'VisualCitation' })
export type VisualCitation = z.infer<typeof visualCitation>

export const factCheck = z
  .object({
    verified: z.boolean(),
    grounding_score: z.number(),
    verified_count: z.number().int(),
    total_count: z.number().int(),
    status: z.string(),
  })
  .meta({ id: 'FactCheck' })
export type FactCheck = z.infer<typeof factCheck>

export const chatUsage = z
  .object({
    tokens_in: z.number().nullable(),
    tokens_out: z.number().nullable(),
    total_tokens: z.number().nullable(),
    usd_cost: z.number().nullable(),
  })
  .meta({ id: 'ChatUsage' })
export type ChatUsage = z.infer<typeof chatUsage>

export const chatScope = z
  .object({ workspace_id: z.uuid(), paper_id: z.uuid().nullable() })
  .meta({ id: 'ChatScope' })
export type ChatScope = z.infer<typeof chatScope>

export const chatEvent = z
  .discriminatedUnion('event', [
    z.object({
      event: z.literal('metadata'),
      data: z.object({ message_id: z.uuid(), session_id: z.uuid(), scope: chatScope }),
    }),
    z.object({ event: z.literal('delta'), data: z.object({ text: z.string() }) }),
    z.object({
      event: z.literal('citations'),
      data: z.object({ items: z.array(paperCitation) }),
    }),
    z.object({
      event: z.literal('visual_citations'),
      data: z.object({ items: z.array(visualCitation) }),
    }),
    z.object({ event: z.literal('fact_check'), data: factCheck }),
    z.object({ event: z.literal('usage'), data: chatUsage }),
    z.object({
      event: z.literal('done'),
      data: z.object({ message_id: z.uuid(), session_id: z.uuid() }),
    }),
    z.object({ event: z.literal('error'), data: problemSchema }),
  ])
  .meta({ id: 'ChatEvent' })
export type ChatEvent = z.infer<typeof chatEvent>

/* --------------------------------- Sessions --------------------------------- */

export const chatTurn = z
  .object({
    id: z.uuid(),
    question: z.string(),
    /**
     * The answer markdown; null while pending/failed. Fenced citation blocks
     * are stripped upstream, but the model's inline `[Page N, …]` markers are
     * not — the UI renders them as chips (`AnswerMarkdown` + `visual_citations`).
     */
    answer: z.string().nullable(),
    status: z.enum(['pending', 'processing', 'completed', 'failed']),
    deep_thinking: z.boolean(),
    visual_citations: z.array(visualCitation),
    fact_check: factCheck.nullable(),
    usage: chatUsage.nullable(),
    error: z.string().nullable(),
    created_at: z.iso.datetime({ offset: true }),
    completed_at: z.iso.datetime({ offset: true }).nullable(),
  })
  .meta({ id: 'ChatTurn' })
export type ChatTurn = z.infer<typeof chatTurn>

export const chatSession = z
  .object({
    id: z.uuid(),
    workspace_id: z.uuid(),
    paper_id: z.uuid().nullable(),
    paper_title: z.string().nullable(),
    title: z.string(),
    summary: z.string().nullable(),
    turns_count: z.number().int(),
    created_at: z.iso.datetime({ offset: true }),
    updated_at: z.iso.datetime({ offset: true }),
  })
  .meta({ id: 'ChatSession' })
export type ChatSession = z.infer<typeof chatSession>

export const chatSessionDetail = chatSession
  .extend({ turns: z.array(chatTurn) })
  .meta({ id: 'ChatSessionDetail' })
export type ChatSessionDetail = z.infer<typeof chatSessionDetail>

export const sessionsQuery = listQuery.extend({
  workspace_id: z.uuid().optional(),
  paper_id: z.uuid().optional(),
  /**
   * Only the caller's own sessions. Django lists every session in a
   * workspace to its admins and managers; a surface that resumes a thread
   * on the reader's behalf must never resume a colleague's.
   */
  mine: z.enum(['1']).optional(),
})
export type SessionsQuery = z.infer<typeof sessionsQuery>

export const sessionPage = pageSchema(chatSession).meta({ id: 'ChatSessionPage' })

export const renameRequest = z
  .object({ title: z.string().min(1).max(255) })
  .meta({ id: 'ChatSessionRename' })

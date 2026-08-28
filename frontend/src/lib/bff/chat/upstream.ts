/**
 * zod transcription of Django's chat surface as it exists today
 * (`backend/chat/serializers/*`, `chat/engine/orchestrator.py`). Pure.
 *
 * Notes that shaped this:
 * - One PaperChatMessage row per TURN: it holds both `question` and the
 *   assistant `message` (sender is always 'user' — never model separate rows).
 * - `citations` is never populated by the stream path — do not build on it.
 * - `visual_citations` are page/figure/quote refs INSIDE the session's paper.
 * - `usd_cost` is a Decimal string on messages but a number on the SSE
 *   `usage` frame.
 * - SSE frames: `event: <name>\ndata: <one-line JSON>\n\n`, no id/heartbeat.
 */
import * as z from 'zod'

export const chatSessionDTO = z.looseObject({
  id: z.string(),
  workspace: z.string(),
  paper: z.string().nullable(),
  paper_title: z.string().nullable(),
  paper_doi: z.string().nullable(),
  user: z.number().nullable(),
  title: z.string(),
  summary: z.string().nullable(),
  messages_count: z.number(),
  total_tokens_in: z.number().nullable(),
  total_tokens_out: z.number().nullable(),
  total_tokens: z.number().nullable(),
  total_usd_cost: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const chatMessageDTO = z.looseObject({
  id: z.string(),
  session: z.string(),
  sender: z.string(),
  status: z.string(),
  deep_thinking: z.boolean(),
  llm_model: z.string().nullable(),
  question: z.string(),
  message: z.string().nullable(),
  citations: z.unknown(),
  visual_citations: z.unknown(),
  hallucination_guard: z.unknown(),
  celery_task_id: z.string().nullable(),
  tokens_in: z.number().nullable(),
  tokens_out: z.number().nullable(),
  total_tokens: z.number().nullable(),
  usd_cost: z.string().nullable(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
})

export const chatSessionDetailDTO = chatSessionDTO.extend({
  messages: z.array(chatMessageDTO),
})

/* ------------------------- SSE frame payloads (today) ------------------------ */

export const djangoChatEvent = z.discriminatedUnion('event', [
  z.object({
    event: z.literal('metadata'),
    data: z.looseObject({ message_id: z.string(), session_id: z.string() }),
  }),
  z.object({ event: z.literal('delta'), data: z.looseObject({ delta: z.string() }) }),
  z.object({
    event: z.literal('citations'),
    data: z.looseObject({ citations: z.array(z.unknown()) }),
  }),
  z.object({
    event: z.literal('visual_citations'),
    data: z.looseObject({ visual_citations: z.array(z.unknown()) }),
  }),
  z.object({
    event: z.literal('fact_check'),
    data: z.looseObject({ hallucination_guard: z.unknown() }),
  }),
  z.object({
    event: z.literal('usage'),
    data: z.looseObject({
      tokens_in: z.number().nullable().optional(),
      tokens_out: z.number().nullable().optional(),
      total_tokens: z.number().nullable().optional(),
      usd_cost: z.union([z.number(), z.string()]).nullable().optional(),
    }),
  }),
  z.object({
    event: z.literal('done'),
    data: z.looseObject({ message_id: z.string().optional() }),
  }),
  z.object({ event: z.literal('error'), data: z.looseObject({ error: z.string() }) }),
])
export type DjangoChatEvent = z.infer<typeof djangoChatEvent>

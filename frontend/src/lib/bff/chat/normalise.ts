/**
 * Django chat rows → OUR contract. Pure (no `server-only`), so the mapping is
 * unit-testable; `service.ts` owns the fetches and calls these.
 *
 * One Django message row is one TURN: it holds `question` + `message`
 * (`sender` is always 'user').
 */
import { oneLine } from '@/lib/papers/map'
import type * as z from 'zod'
import type { ChatSession, ChatTurn } from './schema'
import { factCheck, visualCitation } from './schema'
import type { chatMessageDTO, chatSessionDTO } from './upstream'

type SessionDTO = z.infer<typeof chatSessionDTO>
type MessageDTO = z.infer<typeof chatMessageDTO>

const TURN_STATUSES = ['pending', 'processing', 'completed', 'failed', 'aborted'] as const

export function toSession(dto: SessionDTO): ChatSession {
  return {
    id: dto.id,
    workspace_id: dto.workspace,
    paper_id: dto.paper,
    // Django serializes the stored column as-is; sessions never pass through
    // toScoredPaper, and the Ask rail puts this in a `title=` attribute, which
    // HTML does not collapse.
    paper_title: dto.paper_title === null ? null : oneLine(dto.paper_title),
    title: dto.title,
    summary: dto.summary || null,
    turns_count: dto.messages_count,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
  }
}

export function toTurn(dto: MessageDTO): ChatTurn {
  const visuals = Array.isArray(dto.visual_citations)
    ? dto.visual_citations
        .map((v) => visualCitation.safeParse(v))
        .filter((r) => r.success)
        .map((r) => r.data)
    : []
  const guard = factCheck.safeParse(dto.hallucination_guard)
  const hasUsage = dto.tokens_in !== null || dto.tokens_out !== null || dto.total_tokens !== null
  // A status this contract does not know is a failure, never a completed
  // answer; `aborted` (the reader stopped the stream) is a known one.
  const status = TURN_STATUSES.includes(dto.status as never)
    ? (dto.status as ChatTurn['status'])
    : 'failed'
  return {
    id: dto.id,
    question: dto.question,
    answer: dto.message || null,
    status,
    deep_thinking: dto.deep_thinking,
    visual_citations: visuals,
    fact_check: guard.success ? guard.data : null,
    usage: hasUsage
      ? {
          tokens_in: dto.tokens_in,
          tokens_out: dto.tokens_out,
          total_tokens: dto.total_tokens,
          usd_cost: dto.usd_cost !== null && dto.usd_cost !== '' ? Number(dto.usd_cost) : null,
        }
      : null,
    error: dto.error_message || null,
    created_at: dto.created_at,
    completed_at: dto.completed_at,
  }
}

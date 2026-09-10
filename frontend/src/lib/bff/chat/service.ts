/**
 * Chat sessions service. Source `django` (default): today's
 * `/api/chat/sessions/` endpoints, normalised — one Django message row is one
 * TURN (question + answer together). `stub` serves fixtures for offline UI
 * work. Server-only.
 */
import 'server-only'

import { oneLine } from '@/lib/papers/map'
import { cache } from 'react'
import * as z from 'zod'
import { django, djangoVoid } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { settings } from '../settings/service'
import { fixtureSessionDetails, fixtureSessions } from './fixtures'
import type { ChatSession, ChatSessionDetail, ChatTurn, SessionsQuery } from './schema'
import { factCheck, visualCitation } from './schema'
import { chatMessageDTO, chatSessionDetailDTO, chatSessionDTO } from './upstream'

type SessionDTO = z.infer<typeof chatSessionDTO>
type MessageDTO = z.infer<typeof chatMessageDTO>

function toSession(dto: SessionDTO): ChatSession {
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
  const status = (['pending', 'processing', 'completed', 'failed'] as const).includes(
    dto.status as never,
  )
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

const listSessionsRaw = cache(async (filter: string) =>
  django(`/api/chat/sessions/${filter}`, z.array(chatSessionDTO)),
)

export const chat = {
  async listSessions(query: SessionsQuery): Promise<Page<ChatSession>> {
    const extra: Record<string, string> = {}
    if (query.workspace_id) extra.workspace_id = query.workspace_id
    if (query.paper_id) extra.paper_id = query.paper_id
    if (sourceOf('chat') === 'stub') {
      return paginate(fixtureSessions, query, '/bff/chat/sessions', extra)
    }
    const params = new URLSearchParams(extra)
    const [rows, me] = await Promise.all([
      listSessionsRaw(params.size > 0 ? `?${params}` : ''),
      query.mine ? settings.profile() : null,
    ])
    const mine = me ? rows.filter((row) => row.user === me.id) : rows
    if (query.mine) extra.mine = '1'
    return paginate(mine.map(toSession), query, '/bff/chat/sessions', extra)
  },

  async getSession(id: string): Promise<ChatSessionDetail | null> {
    if (sourceOf('chat') === 'stub') return fixtureSessionDetails.find((s) => s.id === id) ?? null
    try {
      const dto = await django(
        `/api/chat/sessions/${assertUuid(id, 'session id')}/`,
        chatSessionDetailDTO,
      )
      return { ...toSession(dto), turns: dto.messages.map(toTurn) }
    } catch (error) {
      if (error instanceof ProblemError && error.problem.status === 404) return null
      throw error
    }
  },

  async deleteSession(id: string): Promise<void> {
    if (sourceOf('chat') === 'stub') return
    await djangoVoid(`/api/chat/sessions/${assertUuid(id, 'session id')}/`, { method: 'DELETE' })
  },

  async renameSession(_id: string, _title: string): Promise<never> {
    // Django routes PATCH but its serializer is all-read-only — a silent
    // no-op. The requested endpoint (see the folder README) makes it save.
    throw problem('not-implemented', {
      detail:
        'Renaming sessions needs backend support: PATCH /api/chat/sessions/{id}/ currently ignores the body.',
    })
  },
}

/**
 * Chat sessions service. Source `django` (default): today's
 * `/api/chat/sessions/` endpoints, normalised — one Django message row is one
 * TURN (question + answer together). `stub` serves fixtures for offline UI
 * work. Server-only.
 */
import 'server-only'

import { cache } from 'react'
import * as z from 'zod'
import { django, djangoVoid } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { settings } from '../settings/service'
import { fixtureSessionDetails, fixtureSessions } from './fixtures'
import { toSession, toTurn } from './normalise'
import type { ChatSession, ChatSessionDetail, SessionsQuery } from './schema'
import { chatSessionDetailDTO, chatSessionDTO } from './upstream'

const listSessionsRaw = cache(async (filter: string) =>
  django(`/api/chat/sessions/${filter}`, z.array(chatSessionDTO)),
)

export const chat = {
  async listSessions(query: SessionsQuery): Promise<Page<ChatSession>> {
    const extra: Record<string, string> = {}
    if (query.workspace_id) extra.workspace_id = query.workspace_id
    if (query.paper_id) extra.paper_id = query.paper_id
    // Upstream takes no `mine` — it is ours — but the pager links must keep
    // it, or page 2 of a scoped list comes back unscoped.
    const params = new URLSearchParams(extra)
    if (query.mine) extra.mine = '1'
    if (sourceOf('chat') === 'stub') {
      return paginate(fixtureSessions, query, '/bff/chat/sessions', extra)
    }
    const [rows, me] = await Promise.all([
      listSessionsRaw(params.size > 0 ? `?${params}` : ''),
      query.mine ? settings.profile() : null,
    ])
    const mine = me ? rows.filter((row) => row.user === me.id) : rows
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

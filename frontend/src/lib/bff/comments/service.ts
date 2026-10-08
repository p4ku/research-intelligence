import 'server-only'

import { cache } from 'react'
import * as z from 'zod'
import { django, djangoVoid } from '../core/http'
import { problem } from '../core/problem'
import { assertUuid } from '../core/validate'
import {
  paperComment,
  toggleReactionResponse,
  type CommentReactionGroup,
  type PaperComment,
} from './schema'

const commentsListSchema = z.union([
  z.array(paperComment),
  z
    .object({
      results: z.array(paperComment),
    })
    .transform((obj) => obj.results),
])

const listCommentsRaw = cache(async (paperId: string) =>
  django(`/api/comments/?paper=${paperId}`, commentsListSchema),
)

export const comments = {
  async list(paperId: string): Promise<PaperComment[]> {
    const validId = assertUuid(paperId, 'paper id')
    const list = await listCommentsRaw(validId)
    return list.filter((c) => !c.is_deleted)
  },

  async create(paperId: string, content: string): Promise<PaperComment> {
    const validId = assertUuid(paperId, 'paper id')
    const trimmed = content.trim()
    if (!trimmed) {
      throw problem('validation', { detail: 'Comment content cannot be empty.' })
    }
    return django('/api/comments/', paperComment, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        paper: validId,
        content: trimmed,
      }),
    })
  },

  async update(commentId: string, content: string): Promise<PaperComment> {
    const validId = assertUuid(commentId, 'comment id')
    const trimmed = content.trim()
    if (!trimmed) {
      throw problem('validation', { detail: 'Comment content cannot be empty.' })
    }
    return django(`/api/comments/${validId}/`, paperComment, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        content: trimmed,
      }),
    })
  },

  async delete(commentId: string): Promise<void> {
    const validId = assertUuid(commentId, 'comment id')
    await djangoVoid(`/api/comments/${validId}/?hard=true`, {
      method: 'DELETE',
    })
  },

  async toggleReaction(
    commentId: string,
    reactionType: string,
  ): Promise<{ action: 'added' | 'removed'; reactions: CommentReactionGroup[] }> {
    const validId = assertUuid(commentId, 'comment id')
    return django(`/api/comments/${validId}/reactions/`, toggleReactionResponse, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ reaction_type: reactionType }),
    })
  },
}

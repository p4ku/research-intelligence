import { describe, expect, test } from 'bun:test'
import * as z from 'zod'
import { commentAuthor, createCommentBody, paperComment, updateCommentBody } from './schema'

const commentsListSchema = z.union([
  z.array(paperComment),
  z.object({ results: z.array(paperComment) }).transform((obj) => obj.results),
])

describe('commentAuthor schema', () => {
  test('parses full author record', () => {
    const raw = {
      id: 12,
      username: 'marie_curie',
      email: 'marie@radium.org',
      name: 'Marie Curie',
    }
    const parsed = commentAuthor.parse(raw)
    expect(parsed.id).toBe(12)
    expect(parsed.username).toBe('marie_curie')
    expect(parsed.name).toBe('Marie Curie')
  })

  test('defaults email and name when not provided', () => {
    const raw = { id: 7, username: 'anonymous_user' }
    const parsed = commentAuthor.parse(raw)
    expect(parsed.email).toBe('')
    expect(parsed.name).toBe('')
  })
})

describe('paperComment schema', () => {
  test('parses valid paper comment', () => {
    const raw = {
      id: '00000000-0000-4000-8000-000000000099',
      paper_id: '00000000-0000-4000-8000-000000000041',
      pipeline_run_id: null,
      user: { id: 1, username: 'reviewer', name: 'Chief Reviewer' },
      content: 'Strong methodology with impressive benchmark results.',
      created_at: '2026-10-08T10:00:00Z',
    }
    const parsed = paperComment.parse(raw)
    expect(parsed.id).toBe('00000000-0000-4000-8000-000000000099')
    expect(parsed.content).toBe('Strong methodology with impressive benchmark results.')
    expect(parsed.is_edited).toBe(false)
    expect(parsed.is_deleted).toBe(false)
  })

  test('preserves is_edited and is_deleted flags', () => {
    const raw = {
      id: '00000000-0000-4000-8000-000000000099',
      user: { id: 1, username: 'reviewer' },
      content: 'Updated observation.',
      created_at: '2026-10-08T10:00:00Z',
      is_edited: true,
      is_deleted: true,
    }
    const parsed = paperComment.parse(raw)
    expect(parsed.is_edited).toBe(true)
    expect(parsed.is_deleted).toBe(true)
  })
})

describe('createCommentBody schema', () => {
  test('accepts non-empty comment', () => {
    const parsed = createCommentBody.parse({ content: 'Valuable dataset insights.' })
    expect(parsed.content).toBe('Valuable dataset insights.')
  })

  test('rejects empty string', () => {
    expect(() => createCommentBody.parse({ content: '' })).toThrow()
  })
})

describe('updateCommentBody schema', () => {
  test('accepts non-empty updated content', () => {
    const parsed = updateCommentBody.parse({ content: 'Revised insights.' })
    expect(parsed.content).toBe('Revised insights.')
  })

  test('rejects empty string on update', () => {
    expect(() => updateCommentBody.parse({ content: '' })).toThrow()
  })
})

describe('commentsListSchema handling DRF envelopes', () => {
  const sampleComment = {
    id: '00000000-0000-4000-8000-000000000001',
    user: { id: 1, username: 'alice' },
    content: 'Interesting finding in section 3',
    created_at: '2026-10-08T12:00:00Z',
  }

  test('unwraps DRF paginated object { results: [...] }', () => {
    const envelope = {
      count: 1,
      next: null,
      previous: null,
      results: [sampleComment],
    }
    const parsed = commentsListSchema.parse(envelope)
    expect(Array.isArray(parsed)).toBe(true)
    expect(parsed.length).toBe(1)
    expect(parsed[0]?.content).toBe('Interesting finding in section 3')
  })

  test('accepts raw array [...] directly', () => {
    const rawList = [sampleComment]
    const parsed = commentsListSchema.parse(rawList)
    expect(Array.isArray(parsed)).toBe(true)
    expect(parsed.length).toBe(1)
    expect(parsed[0]?.id).toBe('00000000-0000-4000-8000-000000000001')
  })
})

describe('comment reactions schema', () => {
  test('parses paperComment with reactions array', () => {
    const raw = {
      id: '00000000-0000-4000-8000-000000000088',
      user: { id: 2, username: 'bob' },
      content: 'Important observation.',
      created_at: '2026-10-08T15:00:00Z',
      reactions: [
        {
          reaction_type: 'thumbs_up',
          count: 3,
          users: ['alice', 'charlie', 'bob'],
          has_reacted: true,
        },
        {
          reaction_type: 'bulb',
          count: 1,
          users: ['alice'],
          has_reacted: false,
        },
      ],
    }
    const parsed = paperComment.parse(raw)
    expect(parsed.reactions).toHaveLength(2)
    expect(parsed.reactions[0]?.reaction_type).toBe('thumbs_up')
    expect(parsed.reactions[0]?.count).toBe(3)
    expect(parsed.reactions[0]?.has_reacted).toBe(true)
    expect(parsed.reactions[1]?.reaction_type).toBe('bulb')
  })

  test('defaults reactions to empty array when omitted', () => {
    const raw = {
      id: '00000000-0000-4000-8000-000000000088',
      user: { id: 2, username: 'bob' },
      content: 'No reactions yet.',
      created_at: '2026-10-08T15:00:00Z',
    }
    const parsed = paperComment.parse(raw)
    expect(parsed.reactions).toEqual([])
  })
})

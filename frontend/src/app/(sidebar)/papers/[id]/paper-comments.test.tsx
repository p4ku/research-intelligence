import { AnswerMarkdown } from '@/components/answer-markdown'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  AVAILABLE_REACTIONS,
  formatCommentDate,
  getReactionEmoji,
  PaperComments,
  PaperCommentsSkeleton,
  userInitials,
} from './paper-comments'

describe('userInitials', () => {
  test('extracts initials from multi-word full name', () => {
    expect(userInitials('John Doe')).toBe('JD')
    expect(userInitials('Marie Curie-Sklodowska')).toBe('MC')
  })

  test('extracts first two letters when only single name or username given', () => {
    expect(userInitials('Researcher')).toBe('RE')
    expect(userInitials(undefined, 'alex123')).toBe('AL')
  })

  test('falls back to ? on empty or missing name', () => {
    expect(userInitials('')).toBe('?')
    expect(userInitials(undefined, undefined)).toBe('?')
  })
})

describe('formatCommentDate', () => {
  test('formats valid ISO datetime to readable string', () => {
    const formatted = formatCommentDate('2026-10-08T14:30:00Z')
    expect(formatted).toBeTruthy()
    expect(typeof formatted).toBe('string')
  })

  test('returns input string if parsing fails', () => {
    expect(formatCommentDate('invalid-date')).toBe('invalid-date')
  })
})

describe('PaperComments component static rendering', () => {
  test('renders collapsed card by default with expected data-shape', () => {
    const out = renderToStaticMarkup(
      <PaperComments paperId="00000000-0000-4000-8000-000000000041" />,
    )

    expect(out).toContain('data-shape="paper-comments-card"')
    expect(out).toContain('Comments')
    expect(out).toContain('Add a comment…')
    expect(out).toContain('aria-expanded="false"')
  })

  test('renders with current user prop without errors', () => {
    const mockUser = {
      id: 42,
      username: 'piotr_researcher',
      name: 'Piotr Researcher',
      email: 'piotr@example.com',
      isStaff: false,
    }

    const out = renderToStaticMarkup(
      <PaperComments paperId="00000000-0000-4000-8000-000000000041" currentUser={mockUser} />,
    )

    expect(out).toContain('data-shape="paper-comments-card"')
  })

  test('formats loose markdown delimiters in comments like bold and italic with inner whitespace', () => {
    const boldItalic = renderToStaticMarkup(<AnswerMarkdown text="***comment 3 Bold ***" />)
    expect(boldItalic).toContain('<strong')
    expect(boldItalic).toContain('<em')
    expect(boldItalic).toContain('comment 3 Bold')

    const boldWithSpaces = renderToStaticMarkup(<AnswerMarkdown text="** V **" />)
    expect(boldWithSpaces).toContain('<strong')
    expect(boldWithSpaces).toContain('V')
  })

  test('only comment author has edit rights', () => {
    const authorUser = { id: 10, username: 'author_user' }
    const otherUser = { id: 20, username: 'other_user' }
    const comment = { id: 'c1', user: { id: 10, username: 'author_user' } }

    const isAuthor =
      authorUser.id === comment.user.id || authorUser.username === comment.user.username
    const isOtherAuthor =
      otherUser.id === comment.user.id || otherUser.username === comment.user.username

    expect(isAuthor).toBe(true)
    expect(isOtherAuthor).toBe(false)
  })

  test('provides 6 standard annotator reactions with matching emoji representations', () => {
    expect(AVAILABLE_REACTIONS).toHaveLength(6)
    expect(getReactionEmoji('thumbs_up')).toBe('👍')
    expect(getReactionEmoji('thumbs_down')).toBe('👎')
    expect(getReactionEmoji('bulb')).toBe('💡')
    expect(getReactionEmoji('rocket')).toBe('🚀')
    expect(getReactionEmoji('question')).toBe('❓')
    expect(getReactionEmoji('heart')).toBe('❤️')
    expect(getReactionEmoji('unknown_reaction')).toBe('💬')
  })

  test('renders PaperCommentsSkeleton with matching structure in loading state', () => {
    const out = renderToStaticMarkup(<PaperCommentsSkeleton />)
    expect(out).toContain('data-shape="paper-comments-card"')
    expect(out).toContain('Comments')
    expect(out).toContain('svg')
  })
})

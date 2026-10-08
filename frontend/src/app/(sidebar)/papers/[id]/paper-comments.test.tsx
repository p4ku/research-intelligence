import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { formatCommentDate, PaperComments, userInitials } from './paper-comments'

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
})

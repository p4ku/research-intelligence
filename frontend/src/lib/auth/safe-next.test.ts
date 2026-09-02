import { describe, expect, test } from 'bun:test'
import { safeNext } from './safe-next'

describe('safeNext', () => {
  test('keeps a local path, query included', () => {
    expect(safeNext('/ask?x=1')).toBe('/ask?x=1')
    expect(safeNext('/dashboard')).toBe('/dashboard')
    expect(safeNext('/papers/42')).toBe('/papers/42')
  })

  test('rejects absolute URLs', () => {
    expect(safeNext('https://evil.example')).toBe('/dashboard')
    expect(safeNext('http://evil.example/')).toBe('/dashboard')
  })

  test('rejects protocol-relative and backslash forms', () => {
    expect(safeNext('//evil.com')).toBe('/dashboard')
    expect(safeNext('/\\evil.com')).toBe('/dashboard')
    expect(safeNext('/a\\b')).toBe('/dashboard')
  })

  test('rejects URL-parser whitespace smuggling', () => {
    // The WHATWG URL parser strips tab/newline/CR anywhere in the input, so
    // '/\t/evil.com' resolves to https://evil.com — these must never pass.
    expect(safeNext('/\t/evil.com')).toBe('/dashboard')
    expect(safeNext('/\n/evil.com')).toBe('/dashboard')
    expect(safeNext('/\r/evil.com')).toBe('/dashboard')
  })

  test('rejects /auth targets (sign-in → logout loops)', () => {
    expect(safeNext('/auth')).toBe('/dashboard')
    expect(safeNext('/auth/login')).toBe('/dashboard')
    expect(safeNext('/auth/logout')).toBe('/dashboard')
  })

  test('rejects empty and missing values', () => {
    expect(safeNext(undefined)).toBe('/dashboard')
    expect(safeNext(null)).toBe('/dashboard')
    expect(safeNext('')).toBe('/dashboard')
    expect(safeNext('ask')).toBe('/dashboard')
  })
})

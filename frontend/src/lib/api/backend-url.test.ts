import { describe, expect, test } from 'bun:test'
import { backendUrl, isTransientNetworkError } from './backend-url'

describe('backendUrl', () => {
  const originalInternal = process.env.BACKEND_INTERNAL_URL
  const originalPublic = process.env.NEXT_PUBLIC_API_URL

  test('falls back to default localhost:8000 when unset', () => {
    delete process.env.BACKEND_INTERNAL_URL
    delete process.env.NEXT_PUBLIC_API_URL
    expect(backendUrl()).toBe('http://localhost:8000')
    process.env.BACKEND_INTERNAL_URL = originalInternal
    process.env.NEXT_PUBLIC_API_URL = originalPublic
  })

  test('reads BACKEND_INTERNAL_URL and strips trailing slash', () => {
    process.env.BACKEND_INTERNAL_URL = 'https://sri-prod.apps.01.cf.eu01.onstackit.cloud///'
    expect(backendUrl()).toBe('https://sri-prod.apps.01.cf.eu01.onstackit.cloud')
    process.env.BACKEND_INTERNAL_URL = originalInternal
  })
})

describe('isTransientNetworkError', () => {
  test('recognizes EAI_AGAIN DNS timeout from cause', () => {
    const error = new TypeError('fetch failed')
    ;(error as unknown as Record<string, unknown>).cause = {
      code: 'EAI_AGAIN',
      syscall: 'getaddrinfo',
      hostname: 'research-scanner.schwarz',
    }
    expect(isTransientNetworkError(error)).toBe(true)
  })

  test('recognizes ECONNRESET and ETIMEDOUT', () => {
    const econnreset = new Error('read ECONNRESET')
    ;(econnreset as unknown as Record<string, unknown>).code = 'ECONNRESET'
    expect(isTransientNetworkError(econnreset)).toBe(true)

    const etimedout = new Error('connect ETIMEDOUT')
    ;(etimedout as unknown as Record<string, unknown>).code = 'ETIMEDOUT'
    expect(isTransientNetworkError(etimedout)).toBe(true)
  })

  test('recognizes generic fetch failed messages', () => {
    expect(isTransientNetworkError(new TypeError('fetch failed'))).toBe(true)
  })

  test('returns false for non-network errors or null', () => {
    expect(isTransientNetworkError(null)).toBe(false)
    expect(isTransientNetworkError(undefined)).toBe(false)
    expect(isTransientNetworkError(new Error('SyntaxError: unexpected token'))).toBe(false)
  })
})

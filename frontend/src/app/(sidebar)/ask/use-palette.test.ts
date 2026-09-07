/**
 * The palette's one automatic retry: which failures earn it, how the second
 * request announces itself on the wire, and that there is never a third.
 */
import { BffClientError } from '@/lib/bff/client'
import { problemBody } from '@/lib/bff/core/problem'
import { afterAll, afterEach, describe, expect, spyOn, test } from 'bun:test'
import { failureSlug, isTransient, paletteUrl, withOneRetry } from './use-palette'

const failure = (slug: Parameters<typeof problemBody>[0]) =>
  new BffClientError(problemBody(slug, { instance: '/bff/papers/palette' }))

describe('isTransient', () => {
  test('an outage earns a second attempt', () => {
    expect(isTransient(failure('upstream-unavailable'))).toBe(true)
    expect(isTransient(failure('upstream-error'))).toBe(true)
    expect(isTransient(failure('internal'))).toBe(true)
  })

  test('so does anything that is not a typed problem', () => {
    expect(isTransient(new TypeError('Failed to fetch'))).toBe(true)
  })

  test('a 4xx does not: the same request would fail the same way', () => {
    expect(isTransient(failure('unauthenticated'))).toBe(false)
    expect(isTransient(failure('forbidden'))).toBe(false)
    expect(isTransient(failure('validation'))).toBe(false)
  })
})

describe('failureSlug', () => {
  test('names the problem', () => {
    expect(failureSlug(failure('upstream-error'))).toBe('upstream-error')
  })

  test('names a timed-out fetch', () => {
    expect(failureSlug(new DOMException('The operation timed out.', 'TimeoutError'))).toBe(
      'timeout',
    )
  })

  test('falls back for an untyped error', () => {
    expect(failureSlug(new Error('boom'))).toBe('unknown')
  })
})

describe('paletteUrl', () => {
  test('the first request is bare', () => {
    expect(paletteUrl()).toBe('/bff/papers/palette')
  })

  test('the retry carries its reason', () => {
    expect(paletteUrl('upstream-error')).toBe('/bff/papers/palette?retry=1&after=upstream-error')
  })

  test('the reason is a slug and nothing else — it is written to a log', () => {
    expect(paletteUrl('x\n[bff] GET /bff/y → 500')).toBe(
      '/bff/papers/palette?retry=1&after=xbffbffy500',
    )
    expect(paletteUrl('\n\n')).toBe('/bff/papers/palette')
    expect(paletteUrl('a'.repeat(80))).toBe(`/bff/papers/palette?retry=1&after=${'a'.repeat(64)}`)
  })
})

describe('withOneRetry', () => {
  // bun runs every test file in one process: restore, or the mock outlives this file.
  const warn = spyOn(console, 'warn').mockImplementation(() => {})
  afterEach(() => warn.mockClear())
  afterAll(() => warn.mockRestore())

  /** A loader scripted with its outcomes, in order; records what it was told. */
  function scripted(outcomes: (Error | string)[]) {
    const calls: (string | undefined)[] = []
    const load = (retryAfter?: string) => {
      calls.push(retryAfter)
      const next = outcomes.shift()
      return next instanceof Error ? Promise.reject(next) : Promise.resolve(next ?? 'none')
    }
    return { load, calls }
  }

  test('a transient failure is retried once, told what went wrong, and logged', async () => {
    const { load, calls } = scripted([failure('upstream-error'), 'papers'])
    expect(await withOneRetry(load, 0)).toBe('papers')
    expect(calls).toEqual([undefined, 'upstream-error'])
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0]?.[0])).toContain('upstream-error')
  })

  test('a second failure is surfaced, not retried again', async () => {
    const first = failure('upstream-unavailable')
    const second = failure('upstream-error')
    const { load, calls } = scripted([first, second])
    await expect(withOneRetry(load, 0)).rejects.toBe(second)
    expect(calls).toHaveLength(2)
  })

  test('a 4xx is surfaced at once', async () => {
    const forbidden = failure('forbidden')
    const { load, calls } = scripted([forbidden, 'never'])
    await expect(withOneRetry(load, 0)).rejects.toBe(forbidden)
    expect(calls).toEqual([undefined])
    expect(warn).not.toHaveBeenCalled()
  })

  test('a clean load never retries', async () => {
    const { load, calls } = scripted(['papers'])
    expect(await withOneRetry(load, 0)).toBe('papers')
    expect(calls).toEqual([undefined])
  })
})

/**
 * Pins error-UX audit #2: a backend failure must stay distinguishable from an
 * empty list. workspaces.listAllResult() is a thin wrapper over this.
 */
import { describe, expect, test } from 'bun:test'
import { problem } from './problem'
import { problemResult } from './result'

describe('problemResult', () => {
  test('a 502 resolves to {ok: false} with the problem, not an empty value', async () => {
    const result = await problemResult(Promise.reject(problem('upstream-unavailable')))
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.problem.status).toBe(502)
  })

  test('an empty list is still ok — absence is not an outage', async () => {
    const result = await problemResult(Promise.resolve([]))
    expect(result).toEqual({ ok: true, value: [] })
  })

  test('a 401 rethrows so forPage can route it to logout', async () => {
    await expect(problemResult(Promise.reject(problem('unauthenticated')))).rejects.toThrow(
      'Not signed in',
    )
  })

  test('a programming error rethrows — it should crash the boundary, not become a notice', async () => {
    await expect(problemResult(Promise.reject(new TypeError('boom')))).rejects.toThrow('boom')
  })
})

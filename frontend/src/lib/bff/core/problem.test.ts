import { describe, expect, test } from 'bun:test'
import { asProblem, fromUpstream, problem, problemBody, upstreamFieldErrors } from './problem'

describe('problemBody', () => {
  test('builds the slug catalogue shape', () => {
    expect(problemBody('not-found')).toEqual({
      type: '/problems/not-found',
      title: 'Not found',
      status: 404,
    })
  })
  test('extras override', () => {
    const p = problemBody('validation', { detail: 'Nope.' })
    expect(p.status).toBe(400)
    expect(p.detail).toBe('Nope.')
  })
})

describe('fromUpstream', () => {
  test('Django {error} 400 → validation with detail', () => {
    const p = fromUpstream(400, {
      error: 'Either paper_id or workspace_id must be provided.',
    }).problem
    expect(p.type).toBe('/problems/validation')
    expect(p.detail).toContain('paper_id')
  })
  test('DRF field errors 400 → errors map', () => {
    const p = fromUpstream(400, { question: ['This field is required.'] }).problem
    expect(p.errors).toEqual({ question: ['This field is required.'] })
  })
  test('401 → unauthenticated', () => {
    expect(fromUpstream(401, null).problem.type).toBe('/problems/unauthenticated')
  })
  test('403 {error} → forbidden', () => {
    const p = fromUpstream(403, { error: 'no access' }).problem
    expect(p.type).toBe('/problems/forbidden')
    expect(p.detail).toBe('no access')
  })
  test('404 → not-found', () => {
    expect(fromUpstream(404, { error: "Paper 'x' not found." }).problem.status).toBe(404)
  })
  test('500 → upstream-error 502', () => {
    const p = fromUpstream(500, 'Server Error (500)').problem
    expect(p.type).toBe('/problems/upstream-error')
    expect(p.status).toBe(502)
  })
})

describe('upstreamFieldErrors', () => {
  test('ignores error/detail keys and non-string values', () => {
    expect(upstreamFieldErrors({ error: 'x', count: 3, name: ['bad'] })).toEqual({ name: ['bad'] })
  })
  test('undefined when empty', () => {
    expect(upstreamFieldErrors({ error: 'x' })).toBeUndefined()
  })
})

describe('asProblem', () => {
  test('passes ProblemError through with instance', () => {
    const p = asProblem(problem('conflict'), '/bff/papers')
    expect(p.status).toBe(409)
    expect(p.instance).toBe('/bff/papers')
  })
  test('wraps unknown errors as internal', () => {
    expect(asProblem(new Error('boom')).status).toBe(500)
  })
})

import { describe, expect, test } from 'bun:test'
import { fromUpstream, problem, ProblemError } from '../core/problem'
import { abortProblem } from './abort'

const asProblem = (value: unknown): ProblemError => {
  expect(value).toBeInstanceOf(ProblemError)
  return value as ProblemError
}

describe('abortProblem', () => {
  test('a run that ended first is a conflict, not a validation error', () => {
    const detail = "Error: PipelineRun 'abc' is already in status 'completed'."
    const mapped = asProblem(abortProblem(fromUpstream(400, { error: detail })))
    expect(mapped.problem.type).toBe('/problems/conflict')
    expect(mapped.problem.status).toBe(409)
    expect(mapped.problem.detail).toBe(detail)
  })

  test("a caller below manager is forbidden, whatever Django's status code", () => {
    const detail =
      "Error: Insufficient workspace permissions. Role 'researcher' required to be one of ['admin', 'manager'] for workspace 'x'."
    const mapped = asProblem(abortProblem(fromUpstream(400, { error: detail })))
    expect(mapped.problem.type).toBe('/problems/forbidden')
    expect(mapped.problem.status).toBe(403)
  })

  test('an unknown 400 sentence never surfaces as validation prose', () => {
    const mapped = asProblem(
      abortProblem(fromUpstream(400, { error: 'Error: something new happened.' })),
    )
    expect(mapped.problem.type).toBe('/problems/upstream-error')
    expect(mapped.problem.status).toBe(502)
  })

  test('every other failure passes through as the same instance', () => {
    for (const original of [
      fromUpstream(403, { detail: 'Forbidden.' }),
      fromUpstream(404, { detail: 'Not found.' }),
      fromUpstream(500, 'boom'),
      problem('upstream-unavailable'),
      new Error('network'),
    ]) {
      expect(abortProblem(original)).toBe(original)
    }
  })
})

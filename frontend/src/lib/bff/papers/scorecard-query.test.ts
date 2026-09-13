import { describe, expect, test } from 'bun:test'
import { scorecardQuery } from './scorecard-query'

describe('scorecardQuery', () => {
  test('asks for one copy of the list even with no scope', () => {
    expect(scorecardQuery()).toBe('results_only=true')
    expect(scorecardQuery({})).toBe('results_only=true')
  })

  test('narrows to a run, and within it to the papers that passed', () => {
    expect(scorecardQuery({ runId: 'run-1' })).toBe('results_only=true&run_id=run-1')
    expect(scorecardQuery({ runId: 'run-1', screening: 'passed' })).toBe(
      'results_only=true&run_id=run-1&screening=passed',
    )
  })

  test('a run id is escaped, so a hand-made id cannot open a second parameter', () => {
    expect(scorecardQuery({ runId: 'a&screening=all' })).toBe(
      'results_only=true&run_id=a%26screening%3Dall',
    )
  })

  test('extra parameters come first, in the order the caller wrote it', () => {
    expect(scorecardQuery({ runId: 'run-1' }, 'ordering=-created_at')).toBe(
      'ordering=-created_at&results_only=true&run_id=run-1',
    )
  })
})

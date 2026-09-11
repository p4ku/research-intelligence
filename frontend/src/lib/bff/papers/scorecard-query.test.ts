import { describe, expect, test } from 'bun:test'
import { hasScorecardList, scorecardQuery, scorecardRows } from './scorecard-query'

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

  test('paging comes first, in the order the caller wrote it', () => {
    expect(scorecardQuery({ runId: 'run-1' }, 'page=2', 'page_size=200')).toBe(
      'page=2&page_size=200&results_only=true&run_id=run-1',
    )
  })
})

describe('scorecardRows', () => {
  test('reads the list from whichever key the backend sent it under', () => {
    expect(scorecardRows({ results: [1, 2] })).toEqual([1, 2])
    expect(scorecardRows({ papers: [1, 2] })).toEqual([1, 2])
    // Both keys carry the same list when `results_only` was not honoured.
    expect(scorecardRows({ papers: [1, 2], results: [1, 2] })).toEqual([1, 2])
  })

  test('no list is an empty scorecard, not a failure', () => {
    expect(scorecardRows({})).toEqual([])
  })
})

describe('hasScorecardList', () => {
  test('either key is a list, and an empty one still counts', () => {
    expect(hasScorecardList({ results: [] })).toBe(true)
    expect(hasScorecardList({ papers: [] })).toBe(true)
    expect(hasScorecardList({ papers: [1], results: [1] })).toBe(true)
  })

  test('neither key is a broken contract, not an empty corpus', () => {
    expect(hasScorecardList({})).toBe(false)
  })
})

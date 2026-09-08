import { describe, expect, test } from 'bun:test'
import { paperHref } from './href'

describe('paperHref', () => {
  test('the bare permalink without a run', () => {
    expect(paperHref('p1')).toBe('/papers/p1')
    expect(paperHref('p1', {})).toBe('/papers/p1')
    expect(paperHref('p1', { runId: undefined })).toBe('/papers/p1')
  })

  test('the run rides in the query', () => {
    expect(paperHref('p1', { runId: 'r1' })).toBe('/papers/p1?run=r1')
  })
})

import { describe, expect, test } from 'bun:test'
import { byValueAsc, byValueDesc, isResearchMetrics, unionDefinitions } from './select'
import type { DefinitionSummary } from './types'

describe('isResearchMetrics', () => {
  test('matches the prod key and any name that says research metrics', () => {
    expect(
      isResearchMetrics({ key: 'research_metrics', name: 'Research Metrics', is_trl: false }),
    ).toBe(true)
    expect(
      isResearchMetrics({ key: 'quality', name: 'Research metrics (v2)', is_trl: false }),
    ).toBe(true)
    expect(isResearchMetrics({ key: 'rm', name: 'Research-Metrics', is_trl: false })).toBe(true)
  })
  test('leaves the other scoring definitions alone', () => {
    expect(isResearchMetrics({ key: 'nrm', name: 'Non-research metrics', is_trl: false })).toBe(
      false,
    )
    expect(isResearchMetrics({ key: 'schwarz_fit', name: 'Schwarz Fit', is_trl: false })).toBe(
      false,
    )
    expect(isResearchMetrics({ key: 'research_metrics', name: 'TRL', is_trl: true })).toBe(false)
    expect(isResearchMetrics({ key: 'novelty_score', name: 'Novelty Score', is_trl: false })).toBe(
      false,
    )
  })
})

describe('byValueDesc / byValueAsc', () => {
  const values = [5, null, 3, 8, null, 1]
  test('descending, nulls last', () => {
    expect([...values].sort(byValueDesc)).toEqual([8, 5, 3, 1, null, null])
  })
  test('ascending keeps nulls last (regression: flipping the args put them first)', () => {
    expect([...values].sort(byValueAsc)).toEqual([1, 3, 5, 8, null, null])
  })
})

describe('unionDefinitions', () => {
  const def = (key: string, name = key): DefinitionSummary => ({
    id: `00000000-0000-4000-8000-${key.padStart(12, '0')}`,
    name,
    key,
    is_active: true,
    is_trl: false,
    max: null,
  })
  test("lists each key once, in first-seen order, keeping the first domain's entry", () => {
    const union = unionDefinitions([
      { definitions: [def('trl', 'TRL'), def('novelty', 'Novelty')] },
      { definitions: [def('novelty', 'Novelty (B)'), def('maturity')] },
    ])
    expect(union.map((d) => d.key)).toEqual(['trl', 'novelty', 'maturity'])
    expect(union[1].name).toBe('Novelty')
  })
  test('is empty for no domains', () => {
    expect(unionDefinitions([])).toEqual([])
  })
})

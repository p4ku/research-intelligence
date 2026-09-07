import { describe, expect, test } from 'bun:test'
import { byValueAsc, byValueDesc, unionDefinitions } from './select'
import type { DefinitionSummary } from './types'

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

import { describe, expect, test } from 'bun:test'
import { byValueAsc, byValueDesc, trimTitle, unionDefinitions } from './select'
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

describe('trimTitle', () => {
  test('preserves titles with 50 or fewer characters', () => {
    expect(trimTitle('Quantum Computing')).toBe('Quantum Computing')
    expect(trimTitle('a'.repeat(50))).toBe('a'.repeat(50))
  })

  test('trims titles longer than 50 characters to 50 chars with ellipsis', () => {
    const title = 'Ambient Diffusion Policy: Imitation Learning from Suboptimal Data in Robotics'
    expect(trimTitle(title)).toBe('Ambient Diffusion Policy: Imitation Learning from...')
  })

  test('trims trailing whitespace before appending ellipsis', () => {
    const title = 'Short word before cut   and more text that exceeds fifty chars'
    const trimmed = trimTitle(title, 23)
    expect(trimmed).toBe('Short word before cut...')
  })

  test('handles empty or blank string safely', () => {
    expect(trimTitle('')).toBe('')
    expect(trimTitle('   ')).toBe('')
  })
})

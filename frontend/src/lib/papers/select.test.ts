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

  test('cuts a long title at the last word inside the budget, with the ellipsis glyph', () => {
    const title = 'Ambient Diffusion Policy: Imitation Learning from Suboptimal Data in Robotics'
    expect(trimTitle(title)).toBe('Ambient Diffusion Policy: Imitation Learning from…')
    expect(trimTitle(title)).not.toContain('...')
  })

  test('never ends mid-word when a boundary sits in the second half', () => {
    const title = 'Short word before cut and more text that exceeds fifty chars'
    // A 23-char budget lands inside "and"; back up to the space before it.
    expect(trimTitle(title, 23)).toBe('Short word before cut…')
  })

  test('falls back to a hard cut when the only boundary is in the first half', () => {
    const title = 'Ab Supercalifragilisticexpialidocious-words-without-spaces'
    expect(trimTitle(title, 20)).toBe('Ab Supercalifragilis…')
  })

  test('drops trailing whitespace before the ellipsis', () => {
    expect(trimTitle('Short word before cut   and more text that exceeds fifty chars', 24)).toBe(
      'Short word before cut…',
    )
  })

  test('handles empty or blank string safely', () => {
    expect(trimTitle('')).toBe('')
    expect(trimTitle('   ')).toBe('')
  })
})

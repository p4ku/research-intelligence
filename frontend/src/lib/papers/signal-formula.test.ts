import { describe, expect, test } from 'bun:test'
import { evaluate, ledgerInputs, readInputs, recognisedSnippet } from './signal-formula'

const PROD = `# Jeśli TRL jest zbyt niski, odrzuć ze scoringu
if trl_level < 3.0:
    return 0.0
base = 0.6 * fit_score + 0.4 * novelty_score
multiplier = 1.25 if trl_level >= 7.0 else 1.0
return round(base * multiplier, 2)`

describe('recognisedSnippet', () => {
  test('the production snippet, comment and indentation included', () => {
    expect(recognisedSnippet(PROD)).toBe(true)
    expect(recognisedSnippet(PROD.replace(/ {4}/g, '\t').replace(' * ', '  *  '))).toBe(true)
  })
  test('anything else is not', () => {
    expect(recognisedSnippet(null)).toBe(false)
    expect(recognisedSnippet('')).toBe(false)
    expect(recognisedSnippet(PROD.replace('0.6', '0.7'))).toBe(false)
    expect(recognisedSnippet(PROD + '\nreturn 1')).toBe(false)
  })
})

describe('evaluate (parity with the snippet on real records)', () => {
  test('HybridGen: trl 4, fit 82, novelty 68 → 76.4', () => {
    expect(evaluate({ trl: 4, fit: 82, novelty: 68 })).toMatchObject({
      gate: true,
      fitPart: 49.2,
      noveltyPart: 27.2,
      multiplier: 1,
      bonus: 0,
      score: 76.4,
    })
  })
  test('OMLT: trl 4, fit 62, novelty 45 → 55.2', () => {
    expect(evaluate({ trl: 4, fit: 62, novelty: 45 }).score).toBe(55.2)
  })
  test('gate: trl 2 → 0 regardless of the rest', () => {
    expect(evaluate({ trl: 2, fit: 100, novelty: 100 })).toMatchObject({ gate: false, score: 0 })
  })
  test('bonus: trl 7 multiplies by 1.25', () => {
    expect(evaluate({ trl: 7, fit: 82, novelty: 68 })).toMatchObject({
      multiplier: 1.25,
      bonus: 19.1,
      score: 95.5,
    })
  })
})

describe('readInputs', () => {
  test('numbers and numeric strings; missing → null', () => {
    expect(readInputs({ trl_level: 4, fit_score: '82', novelty_score: 68 })).toEqual({
      trl: 4,
      fit: 82,
      novelty: 68,
    })
    expect(readInputs({ trl_level: 4, fit_score: 82 })).toBeNull()
    expect(readInputs({ trl_level: 'n/a', fit_score: 82, novelty_score: 68 })).toBeNull()
    expect(readInputs(null)).toBeNull()
  })
})

describe('ledgerInputs — only when the mirror provably applies', () => {
  const vars = { trl_level: 4, fit_score: 82, novelty_score: 68 }
  test('recognised snippet + inputs reproduce the stored score', () => {
    expect(ledgerInputs(PROD, vars, 76.4)).toEqual({ trl: 4, fit: 82, novelty: 68 })
  })
  test('stored score disagrees with the mirror → null', () => {
    expect(ledgerInputs(PROD, vars, 70)).toBeNull()
  })
  test('unknown snippet, missing inputs, or unscored → null', () => {
    expect(ledgerInputs(PROD.replace('0.4', '0.5'), vars, 76.4)).toBeNull()
    expect(ledgerInputs(PROD, { trl_level: 4 }, 76.4)).toBeNull()
    expect(ledgerInputs(PROD, vars, null)).toBeNull()
  })
})

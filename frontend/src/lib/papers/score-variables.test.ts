import { describe, expect, test } from 'bun:test'
import {
  classifyVariable,
  formatVariable,
  formulaIdentifiers,
  groupVariables,
  humanise,
  parsePythonList,
} from './score-variables'

// The snippet prod ran on 2026-08-31 (Polish comment and all).
const SNIPPET = `# Jeśli TRL jest zbyt niski, odrzuć ze scoringu
if trl_level < 3.0:
    return 0.0
base = 0.6 * fit_score + 0.4 * novelty_score
multiplier = 1.25 if trl_level >= 7.0 else 1.0
return round(base * multiplier, 2)`

describe('formulaIdentifiers', () => {
  test('reads identifiers in order of first use, skipping keywords, builtins and comments', () => {
    expect(formulaIdentifiers(SNIPPET)).toEqual([
      'trl_level',
      'base',
      'fit_score',
      'novelty_score',
      'multiplier',
    ])
  })
  test('null / empty → []', () => {
    expect(formulaIdentifiers(null)).toEqual([])
    expect(formulaIdentifiers('')).toEqual([])
  })
})

describe('parsePythonList', () => {
  test('single-quoted items, double-quoted items, mixed', () => {
    expect(parsePythonList("['a', 'b c']")).toEqual(['a', 'b c'])
    expect(parsePythonList('["a", "b"]')).toEqual(['a', 'b'])
    expect(parsePythonList(`['a', "it's"]`)).toEqual(['a', "it's"])
  })
  test('escaped quotes inside an item', () => {
    expect(parsePythonList(String.raw`['don\'t', 'x']`)).toEqual(["don't", 'x'])
  })
  test('empty list', () => {
    expect(parsePythonList('[]')).toEqual([])
  })
  test('not a list of strings → null', () => {
    expect(parsePythonList('plain text')).toBeNull()
    expect(parsePythonList('[1, 2]')).toBeNull()
    expect(parsePythonList("['unterminated")).toBeNull()
    expect(parsePythonList("['a' 'b']")).toBeNull()
  })
})

describe('classifyVariable', () => {
  test('kinds', () => {
    expect(classifyVariable('rigour', 82).kind).toBe('number')
    expect(classifyVariable('limitations_acknowledged', false).kind).toBe('boolean')
    expect(classifyVariable('rigour_band', 'Strong').kind).toBe('short')
    expect(classifyVariable('decision_category', 'ACCEPTED: Core scope').kind).toBe('short')
    // 26 chars: too wide for a grid cell, so it joins the long tail.
    expect(classifyVariable('decision_category', 'ACCEPTED: Core scope match').kind).toBe('text')
    expect(classifyVariable('k', null).kind).toBe('empty')
    expect(classifyVariable('k', '').kind).toBe('empty')
  })
  test('sentence prose is text even when short', () => {
    expect(classifyVariable('k', 'Broad relevance. Long-context cost matters.').kind).toBe('text')
    expect(classifyVariable('k', 'x'.repeat(25)).kind).toBe('text')
    expect(classifyVariable('k', 'x'.repeat(24)).kind).toBe('short')
  })
  test('python-repr list is parsed', () => {
    const v = classifyVariable('key_outcomes', "['Open-source toolkit', 'Supports NNs']")
    expect(v.kind).toBe('list')
    expect(v.items).toEqual(['Open-source toolkit', 'Supports NNs'])
  })
})

describe('groupVariables', () => {
  test('formula inputs first (snippet order), then scalars, then the long tail', () => {
    const g = groupVariables(
      {
        rigour: 82,
        novelty_score: 68,
        fit_score: 82,
        trl_level: 4,
        rigour_band: 'Strong',
        impact_reach: 'The proposed paradigms are practical. They will be adopted.',
        key_outcomes: 1.41,
        key_contributions: "['A', 'B']",
        limitations_acknowledged: false,
      },
      SNIPPET,
    )
    expect(g.inputs.map((v) => v.key)).toEqual(['trl_level', 'fit_score', 'novelty_score'])
    expect(g.scalars.map((v) => v.key)).toEqual([
      'rigour',
      'rigour_band',
      'key_outcomes',
      'limitations_acknowledged',
    ])
    expect(g.long.map((v) => v.key)).toEqual(['impact_reach', 'key_contributions'])
  })
  test('no snippet → nothing is an input', () => {
    const g = groupVariables({ fit_score: 1, notes: 'a. b. c.' }, null)
    expect(g.inputs).toEqual([])
    expect(g.scalars.map((v) => v.key)).toEqual(['fit_score'])
    expect(g.long.map((v) => v.key)).toEqual(['notes'])
  })
})

describe('humanise', () => {
  test('snake_case → sentence case, acronyms upper', () => {
    expect(humanise('fit_score')).toBe('Fit score')
    expect(humanise('trl_level')).toBe('TRL level')
    expect(humanise('trl_technology_readiness_level')).toBe('TRL technology readiness level')
    expect(humanise('test_e2e_rigour_67911371')).toBe('Test e2e rigour 67911371')
    expect(humanise('Strong')).toBe('Strong')
  })
})

describe('formatVariable', () => {
  const t = (s: string) => (s === 'Yes' ? 'Ja' : s === 'No' ? 'Nein' : s)
  test('numbers keep integers, round floats to 2dp', () => {
    expect(formatVariable(classifyVariable('k', 82))).toBe('82')
    expect(formatVariable(classifyVariable('k', 1.4142))).toBe('1.41')
  })
  test('booleans translate, empties dash', () => {
    expect(formatVariable(classifyVariable('k', true), t)).toBe('Ja')
    expect(formatVariable(classifyVariable('k', false), t)).toBe('Nein')
    expect(formatVariable(classifyVariable('k', null))).toBe('—')
  })
})

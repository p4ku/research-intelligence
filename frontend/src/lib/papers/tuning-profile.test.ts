import type { WorkspaceScoring } from '@/lib/bff/scoring/schema'
import { describe, expect, test } from 'bun:test'
import { fallbackDimensions, tuningProfile } from './tuning-profile'

const PROD = `# Jeśli TRL jest zbyt niski, odrzuć ze scoringu
if trl_level < 3.0:
    return 0.0
base = 0.6 * fit_score + 0.4 * novelty_score
multiplier = 1.25 if trl_level >= 7.0 else 1.0
return round(base * multiplier, 2)`

/** HybridGen from the prod snapshot: trl 4, fit 82, novelty 68 → 76.4. */
function scoring(over: Partial<WorkspaceScoring> = {}): WorkspaceScoring {
  return {
    workspace_id: '00000000-0000-4000-8000-000000000001',
    code: PROD,
    code_source: 'latest_metric',
    variables: [
      { key: 'fit_score', definition_id: null, name: 'Fit score', max: 100, is_trl: false },
      { key: 'novelty_score', definition_id: null, name: 'Novelty score', max: 100, is_trl: false },
      { key: 'trl_level', definition_id: null, name: 'TRL level', max: 9, is_trl: true },
    ],
    weights: [],
    weights_source: 'stub',
    example: {
      paper_id: '00000000-0000-4000-8000-000000000002',
      title: 'HybridGen',
      signal_score: 76.4,
      variables: { trl_level: 4, fit_score: 82, novelty_score: 68 },
    },
    ...over,
  }
}

describe('tuningProfile', () => {
  test('the production snippet, verified against a real record', () => {
    const profile = tuningProfile(scoring())
    expect(profile).not.toBeNull()
    expect(profile).toHaveLength(3)
    expect(profile![0]).toMatchObject({ key: 'fit', kind: 'share', share: 0.6, gate: null })
    expect(profile![1]).toMatchObject({ key: 'novelty', kind: 'share', share: 0.4, gate: null })
    expect(profile![2]).toMatchObject({
      key: 'trl',
      kind: 'gate',
      share: null,
      gate: 3,
      bonusAt: 7,
      bonus: 1.25,
    })
  })

  test('TRL is a gate, never a share — nothing claims a percentage for it', () => {
    const trl = tuningProfile(scoring())!.find((i) => i.key === 'trl')!
    expect(trl.share).toBeNull()
    expect(trl.kind).toBe('gate')
  })

  test('the shares are the ones the score actually uses', () => {
    const shares = tuningProfile(scoring())!
      .filter((i) => i.kind === 'share')
      .map((i) => i.share!)
    expect(shares.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 10)
  })

  test('a changed formula yields no profile rather than a stale 60/40', () => {
    expect(tuningProfile(scoring({ code: PROD.replace('0.6', '0.7') }))).toBeNull()
    expect(tuningProfile(scoring({ code: 'signal_score = fit_score' }))).toBeNull()
    expect(tuningProfile(scoring({ code: null }))).toBeNull()
  })

  test('a stored score the mirror cannot reproduce yields no profile', () => {
    const example = { ...scoring().example!, signal_score: 91.2 }
    expect(tuningProfile(scoring({ example }))).toBeNull()
  })

  test('no example, or an example missing an input, yields no profile', () => {
    expect(tuningProfile(scoring({ example: null }))).toBeNull()
    const partial = { ...scoring().example!, variables: { fit_score: 82, novelty_score: 68 } }
    expect(tuningProfile(scoring({ example: partial }))).toBeNull()
  })

  test('an unscored example paper yields no profile', () => {
    const unscored = { ...scoring().example!, signal_score: null }
    expect(tuningProfile(scoring({ example: unscored }))).toBeNull()
  })
})

describe('fallbackDimensions', () => {
  test('names the workspace definitions, with no influence attached', () => {
    expect(fallbackDimensions(scoring())).toEqual(['Fit score', 'Novelty score', 'TRL level'])
  })
  test('a workspace with no definitions gives an empty list', () => {
    expect(fallbackDimensions(scoring({ variables: [] }))).toEqual([])
  })
})

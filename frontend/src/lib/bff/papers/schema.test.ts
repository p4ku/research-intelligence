import { describe, expect, test } from 'bun:test'
import { fixturePapers } from './fixtures'
import { dimension, editionPaper, scoredPaper, signalScoreDetails } from './schema'
import { signalScoreDetailsDTO } from './upstream'

// Production sends booleans for extraction dimensions such as
// `limitations_acknowledged`; the contract used to accept only number|string
// and every page that composes from /api/papers/ failed with upstream-shape.
const fromProduction = {
  variables: {
    fit_score: 62.0,
    trl_label: 'TRL 4',
    limitations_acknowledged: true,
    evidence_quote: null,
  },
  code_snippet: 'signal_score = fit_score',
  calculated_at: '2026-08-31T08:26:00Z',
  error: null,
}

describe('signal score variables', () => {
  test('contract accepts boolean and null values', () => {
    const parsed = signalScoreDetails.parse(fromProduction)
    expect(parsed.variables.limitations_acknowledged).toBe(true)
    expect(parsed.variables.evidence_quote).toBeNull()
  })

  test('upstream DTO accepts the same', () => {
    expect(signalScoreDetailsDTO.safeParse(fromProduction).success).toBe(true)
  })

  test('still rejects structured values', () => {
    const nested = { ...fromProduction, variables: { weights: { a: 1 } } }
    expect(signalScoreDetails.safeParse(nested).success).toBe(false)
  })
})

// The summary is asked of the backend and not yet served: today's scorecard
// has no such key and must keep parsing; once it lands, the paragraph must
// come through rather than be stripped as an unknown key.
describe('paper summary', () => {
  const base = fixturePapers[0]!

  test('a scorecard without the field parses, summary undefined', () => {
    const { summary: _omitted, ...withoutSummary } = base
    const parsed = scoredPaper.parse(withoutSummary)
    expect(parsed.summary).toBeUndefined()
  })

  test('a served summary comes through, null included', () => {
    expect(scoredPaper.parse({ ...base, summary: 'A control-electronics paper.' }).summary).toBe(
      'A control-electronics paper.',
    )
    expect(scoredPaper.parse({ ...base, summary: null }).summary).toBeNull()
  })
})

// Production papers reach the UI through this parse and no other, so the one
// score rule (lib/papers/score.ts) holds here rather than in any component.
describe('the score rule at the parse seam', () => {
  const base = fixturePapers[0]!
  const edition = { id: base.id, title: base.title, authors: base.authors, source: base.source }
  const failed = { ...base.signal_score_details, error: 'ZeroDivisionError' }

  test('a stored score past the ceiling is capped at 100', () => {
    expect(scoredPaper.parse({ ...base, signal_score: 112.5 }).signal_score).toBe(100)
  })

  test('a failed formula is not scored, whatever zero the scorer wrote', () => {
    const paper = scoredPaper.parse({
      ...base,
      signal_score: 0,
      signal_score_details: failed,
    })
    expect(paper.signal_score).toBeNull()
    // The details still come through — the ledger explains what failed.
    expect(paper.signal_score_details?.error).toBe('ZeroDivisionError')
  })

  test('a real zero survives', () => {
    expect(scoredPaper.parse({ ...base, signal_score: 0 }).signal_score).toBe(0)
  })

  test('a TRL dimension becomes a whole 1–9 level', () => {
    const trl = { key: 'trl_level', definition_id: null, name: 'TRL', max: 9, is_trl: true }
    expect(dimension.parse({ ...trl, value: 6.5 }).value).toBe(7)
    expect(dimension.parse({ ...trl, value: 12 }).value).toBe(9)
    expect(dimension.parse({ ...trl, value: null }).value).toBeNull()
  })

  test('a non-TRL dimension keeps its exact value, over its max included', () => {
    // `max` is inferred and legitimately exceeded; only the bar clamps.
    const parsed = dimension.parse({
      key: 'novelty_score',
      definition_id: null,
      name: 'Novelty Score',
      value: 12.8,
      max: 10,
      is_trl: false,
    })
    expect(parsed.value).toBe(12.8)
  })

  test('an edition paper follows the same rule', () => {
    expect(editionPaper.parse({ ...edition, signal_score: 112.5 }).signal_score).toBe(100)
    expect(
      editionPaper.parse({ ...edition, signal_score: 0, signal_score_details: failed })
        .signal_score,
    ).toBeNull()
  })

  test('an edition row without details keeps its zero — the list endpoint sends none', () => {
    // The editions LIST serializer strips signal_score_details, so a failed
    // formula still reads 0 there until the backend carries the error along
    // (filed for the backend). This pins the hole so the day it closes shows.
    expect(editionPaper.parse({ ...edition, signal_score: 0 }).signal_score).toBe(0)
  })
})

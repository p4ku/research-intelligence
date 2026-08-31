import { describe, expect, test } from 'bun:test'
import { signalScoreDetails } from './schema'
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

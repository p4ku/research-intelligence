import { describe, expect, test } from 'bun:test'
import { errorsFromSubmit } from '../problem-copy'
import { fromUpstream } from './problem'

const t = (s: string) => s

describe('Django error envelopes', () => {
  test('the MCP tools’ {status: "error", error} is a sentence, not a field error', () => {
    // POST /api/pipeline-runs/start/ answers a quota refusal like this, as a 400.
    const err = fromUpstream(400, { status: 'error', error: 'Monthly budget limit exceeded.' })
    expect(err.problem.errors).toBeUndefined()
    expect(errorsFromSubmit(err, ['workspace_id'], t, 'fallback')).toEqual({
      _: 'Monthly budget limit exceeded.',
    })
  })

  test('the custom handler’s {status_code, error, detail} reads the same way', () => {
    const err = fromUpstream(400, { status_code: 400, error: 'Bad dates.', detail: 'Bad dates.' })
    expect(err.problem.errors).toBeUndefined()
    expect(errorsFromSubmit(err, [], t, 'fallback')._).toBe('Bad dates.')
  })

  test('real DRF field errors still paint fields', () => {
    const err = fromUpstream(400, { end_date: ['Must not precede start_date.'] })
    expect(errorsFromSubmit(err, ['end_date'], t, 'fallback')).toEqual({
      end_date: 'Must not precede start_date.',
    })
  })
})

import { describe, expect, test } from 'bun:test'
import { toTurn } from './normalise'

/** A Django message row as `chatMessageDTO` sees it. */
function row(overrides: Record<string, unknown> = {}) {
  return {
    id: '00000000-0000-4000-8000-000000000071',
    session: '00000000-0000-4000-8000-000000000011',
    sender: 'user',
    status: 'completed',
    deep_thinking: false,
    llm_model: 'google/gemini-3.8-flash',
    question: 'What is the energy per synaptic operation?',
    message: 'The optical core dissipates 15 fJ',
    citations: [],
    visual_citations: [],
    hallucination_guard: {},
    celery_task_id: null,
    tokens_in: 800,
    tokens_out: 9,
    total_tokens: 809,
    usd_cost: '0.00060',
    error_message: null,
    created_at: '2026-09-11T09:00:00Z',
    completed_at: '2026-09-11T09:00:04Z',
    ...overrides,
  }
}

describe('toTurn', () => {
  test('a stopped turn keeps its status and the words that had arrived', () => {
    const turn = toTurn(row({ status: 'aborted' }))
    expect(turn.status).toBe('aborted')
    expect(turn.answer).toBe('The optical core dissipates 15 fJ')
    expect(turn.error).toBeNull()
    expect(turn.usage?.usd_cost).toBeCloseTo(0.0006)
  })

  test('an unknown status is still a failure, never a completed answer', () => {
    const turn = toTurn(row({ status: 'exploded', message: '' }))
    expect(turn.status).toBe('failed')
    expect(turn.answer).toBeNull()
  })

  test('a failed turn carries the server reason for the operator, and a null guard', () => {
    const turn = toTurn(
      row({ status: 'failed', message: '', error_message: 'Workspace monthly quota exceeded' }),
    )
    expect(turn.error).toBe('Workspace monthly quota exceeded')
    expect(turn.fact_check).toBeNull()
  })

  test('null verification flags survive as null (the check was skipped, not failed)', () => {
    const turn = toTurn(
      row({
        visual_citations: [{ page: 1, quote: 'only the abstract', verified_in_source: null }],
        hallucination_guard: {
          verified: false,
          grounding_score: 0,
          verified_count: 0,
          total_count: 0,
          status: 'SKIPPED_NO_SOURCE_TEXT',
        },
      }),
    )
    expect(turn.visual_citations[0]?.verified_in_source).toBeNull()
    expect(turn.fact_check?.status).toBe('SKIPPED_NO_SOURCE_TEXT')
  })
})

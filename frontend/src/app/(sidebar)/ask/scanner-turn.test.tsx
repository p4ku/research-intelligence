/**
 * Pins audit offense #5: a failed turn keeps what streamed. The partial text
 * renders above a role="alert" note with exactly one retry action, and the
 * extras (fact check, usage) are suppressed under an unfinished answer.
 */
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { SettledAnswer } from './scanner-turn'
import type { AnswerTurn } from './types'

function turn(overrides: Partial<AnswerTurn>): AnswerTurn {
  return {
    kind: 'answer',
    text: '',
    citations: [],
    visualCitations: [],
    factCheck: {
      verified: true,
      grounding_score: 1,
      verified_count: 3,
      total_count: 3,
      status: 'passed',
    },
    usage: null,
    error: null,
    ...overrides,
  }
}

describe('SettledAnswer on a failed turn', () => {
  test('partial text renders alongside the alert, with one retry action', () => {
    const out = renderToStaticMarkup(
      <SettledAnswer
        turn={turn({ text: 'Three streamed paragraphs', error: 'x' })}
        anchor="vc-0"
        onRetry={() => {}}
      />,
    )
    expect(out).toContain('Three streamed paragraphs')
    expect(out.match(/role="alert"/g)).toHaveLength(1)
    expect(out.match(/Ask again/g)).toHaveLength(1)
    expect(out).toContain('The answer stopped part-way through.')
  })

  test('a failure with no text shows the mapped copy instead', () => {
    const out = renderToStaticMarkup(
      <SettledAnswer
        turn={turn({ error: 'The backend had a problem. Try again in a moment.' })}
        anchor="vc-0"
        onRetry={() => {}}
      />,
    )
    expect(out).toContain('The backend had a problem.')
    expect(out).not.toContain('stopped part-way')
  })

  test('without onRetry there is no action button', () => {
    const out = renderToStaticMarkup(
      <SettledAnswer turn={turn({ text: 'abc', error: 'x' })} anchor="vc-0" />,
    )
    expect(out).not.toContain('Ask again')
  })

  test('extras are suppressed on failure even when fact-check data exists', () => {
    const out = renderToStaticMarkup(
      <SettledAnswer turn={turn({ text: 'abc', error: 'x' })} anchor="vc-0" />,
    )
    expect(out).not.toContain('Fact check')
  })
})

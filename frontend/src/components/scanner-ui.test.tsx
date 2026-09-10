import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { MiniScore, ScoreRow, SignalScore, TrlBadge, scoreColor } from './scanner-ui'

// One rounding rule (10 Sep 2026): every figure prints whole; every band
// reads the exact stored value.

describe('scoreColor', () => {
  test('the band is decided by the exact value, never the printed one', () => {
    expect(scoreColor(75)).toBe('var(--accent)')
    expect(scoreColor(74.96)).toBe('var(--warn)')
    expect(scoreColor(55)).toBe('var(--warn)')
    expect(scoreColor(54.9)).toBe('#9a9a90')
    expect(scoreColor(null)).toBe('#9a9a90')
  })
})

describe('SignalScore', () => {
  test('prints the whole number in the band the exact value earns', () => {
    const out = renderToStaticMarkup(<SignalScore score={74.6} />)
    expect(out).toContain('>75</span>')
    expect(out).toContain('stroke="var(--warn)"')
  })
  test('carries no tooltip with the unrounded figure', () => {
    expect(renderToStaticMarkup(<SignalScore score={74.6} />)).not.toContain('title=')
  })
  test('a missing score is the dash', () => {
    expect(renderToStaticMarkup(<SignalScore score={null} />)).toContain('>—</span>')
  })
})

describe('MiniScore', () => {
  test('whole number with the dot in the exact band', () => {
    const out = renderToStaticMarkup(<MiniScore score={74.6} />)
    expect(out).toContain('>75</span>')
    expect(out).toContain('background-color:var(--warn)')
  })
  test('renders nothing at all without a score', () => {
    expect(renderToStaticMarkup(<MiniScore score={null} />)).toBe('')
  })
})

describe('ScoreRow', () => {
  test('a score-like value prints whole; a small scale keeps its decimals', () => {
    expect(renderToStaticMarkup(<ScoreRow label="Fit" value={61.666666666666664} />)).toContain(
      '>62</span>',
    )
    expect(renderToStaticMarkup(<ScoreRow label="Ratio" value={2.4} max={5} />)).toContain(
      '>2.4/5</span>',
    )
  })
  test('no value shows the raw text, or the dash', () => {
    expect(renderToStaticMarkup(<ScoreRow label="Fit" value={null} raw="n/a" />)).toContain('n/a')
    expect(renderToStaticMarkup(<ScoreRow label="Fit" value={null} />)).toContain('—')
  })
})

describe('TrlBadge', () => {
  test('prints the level it is given with its band', () => {
    const out = renderToStaticMarkup(<TrlBadge trl={7} />)
    expect(out).toContain('TRL 7')
    expect(out).toContain('Deployment')
  })
})

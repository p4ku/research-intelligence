import { describe, expect, test } from 'bun:test'
import {
  SCORE_CEILING,
  SCORE_STEP,
  clampScore,
  normaliseDimension,
  normaliseScore,
  signalScoreOf,
  trlLevel,
} from './score'

describe('clampScore', () => {
  test('holds the 0–100 scale', () => {
    expect(clampScore(112.5)).toBe(100)
    expect(clampScore(-3)).toBe(0)
    expect(clampScore(74.96)).toBe(74.96)
    expect(SCORE_CEILING).toBe(100)
    expect(SCORE_STEP).toBe(5)
  })
})

describe('signalScoreOf', () => {
  test('keeps the exact value below the cap — thresholds read this, not the rounded figure', () => {
    expect(signalScoreOf(74.96)).toBe(74.96)
    expect(signalScoreOf(0)).toBe(0)
  })
  test('caps at 100', () => {
    expect(signalScoreOf(112.5)).toBe(100)
  })
  test('null unless a finite number', () => {
    expect(signalScoreOf(null)).toBeNull()
    expect(signalScoreOf(undefined)).toBeNull()
    expect(signalScoreOf(Number.NaN)).toBeNull()
    expect(signalScoreOf('88')).toBeNull()
  })
  test('a recorded formula error means not scored, whatever number came with it', () => {
    expect(signalScoreOf(0, { error: 'ZeroDivisionError: division by zero' })).toBeNull()
    expect(signalScoreOf(88, { error: 'boom' })).toBeNull()
    expect(signalScoreOf(88, { error: null })).toBe(88)
    expect(signalScoreOf(88, { error: '  ' })).toBe(88)
    expect(signalScoreOf(88, null)).toBe(88)
  })
})

describe('trlLevel', () => {
  test('a whole number from 1 to 9', () => {
    expect(trlLevel(6.5)).toBe(7)
    expect(trlLevel(4.4)).toBe(4)
    expect(trlLevel(0)).toBe(1)
    expect(trlLevel(12)).toBe(9)
  })
})

describe('normaliseDimension', () => {
  test('rounds and clamps TRL only', () => {
    const trl = { key: 'trl', value: 6.5, is_trl: true, max: 9 }
    expect(normaliseDimension(trl)).toEqual({ ...trl, value: 7 })
    const fit = { key: 'fit', value: 61.666666666666664, is_trl: false, max: 100 }
    expect(normaliseDimension(fit)).toBe(fit)
    const over = { key: 'speed', value: 12.8, is_trl: false, max: 10 }
    expect(normaliseDimension(over)).toBe(over)
  })
  test('leaves a missing value alone', () => {
    const trl = { key: 'trl', value: null, is_trl: true }
    expect(normaliseDimension(trl)).toBe(trl)
  })
})

describe('normaliseScore', () => {
  test('caps the Schwarz Score and returns the same object when nothing changes', () => {
    const paper = { id: 'p', signal_score: 87.5, signal_score_details: null }
    expect(normaliseScore(paper)).toBe(paper)
    expect(normaliseScore({ ...paper, signal_score: 112.5 }).signal_score).toBe(100)
  })
  test('a failed formula reads as unscored', () => {
    const failed = {
      id: 'p',
      signal_score: 0,
      signal_score_details: {
        variables: {},
        code_snippet: null,
        calculated_at: null,
        error: 'NameError',
      },
    }
    expect(normaliseScore(failed).signal_score).toBeNull()
  })
  test('works without a details field at all', () => {
    expect(normaliseScore({ signal_score: 140 }).signal_score).toBe(100)
  })
})

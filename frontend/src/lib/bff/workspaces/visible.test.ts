import { describe, expect, test } from 'bun:test'
import { isHiddenWorkspace } from './visible'

describe('isHiddenWorkspace', () => {
  test('hides both spellings, in any case or separator', () => {
    for (const name of [
      'physical-ai-callibration',
      'chip-design-callibration',
      'hybrid-computing-calibration',
      'Calibration',
      'Battery materials (CALLIBRATION)',
    ]) {
      expect(isHiddenWorkspace(name)).toBe(true)
    }
  })

  test('keeps the analysts’ domains', () => {
    for (const name of ['Hybrid Computing', 'Battery materials', 'Physical AI']) {
      expect(isHiddenWorkspace(name)).toBe(false)
    }
  })
})

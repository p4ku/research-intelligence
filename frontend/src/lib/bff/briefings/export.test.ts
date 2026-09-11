import { describe, expect, test } from 'bun:test'
import { pdfText, screeningLogFilename, slugify } from './export'

const NNBSP = String.fromCodePoint(0x202f)
const NBSP = String.fromCodePoint(0xa0)

describe('slugify', () => {
  test('ASCII, lowercase, hyphens; diacritics folded', () => {
    expect(slugify('Hybrid Computing')).toBe('hybrid-computing')
    expect(slugify('Screening-Protokoll')).toBe('screening-protokoll')
    expect(slugify('Künstliche Intelligenz / Chips!')).toBe('kunstliche-intelligenz-chips')
  })
})

describe('screeningLogFilename', () => {
  test('kind, domain, day', () => {
    expect(screeningLogFilename('Screening log', 'Hybrid Computing', '2026-09-10')).toBe(
      'screening-log-hybrid-computing-2026-09-10.pdf',
    )
  })
  test('no domain — a link from before domains were in the URL', () => {
    expect(screeningLogFilename('Screening-Protokoll', undefined, '2026-09-10')).toBe(
      'screening-protokoll-2026-09-10.pdf',
    )
  })
})

describe('pdfText', () => {
  test('narrow and non-breaking spaces become spaces; runs collapse', () => {
    expect(pdfText(`41${NNBSP}%  und${NBSP}mehr`)).toBe('41 % und mehr')
  })
  test('control characters go, paragraph breaks stay, never more than one blank line', () => {
    expect(pdfText(`one\r\ntwo${String.fromCodePoint(7)}\n\n\n\nthree `)).toBe('one\ntwo\n\nthree')
  })
  test('null is empty', () => {
    expect(pdfText(null)).toBe('')
  })
})

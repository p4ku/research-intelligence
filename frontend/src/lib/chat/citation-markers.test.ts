import { describe, expect, test } from 'bun:test'
import {
  extractCitationMarkers,
  holdBackOpenMarker,
  MARKER_RE,
  matchCitations,
  PLACEHOLDER_RE,
} from './citation-markers'

const matches = (s: string) => {
  MARKER_RE.lastIndex = 0
  return MARKER_RE.test(s)
}

describe('MARKER_RE', () => {
  test('accepts the forms the backend prompt and tests use', () => {
    for (const s of [
      '[Page 5, Figure 4, box_2d: [10, 20, 30, 40], quote: "across 64 waveguides"]',
      '[Page 4, Figure 3a, quote: "100 GHz modulated optical clock frequency"]',
      '[Page 1, Fig 1]',
      '[Page 1, Table 1, quote: "99.4% gate fidelity"]',
      '[Page 7, Fig 4b, box_2d: [320, 150, 680, 890], quote: "exact evidence sentence"]',
      '[page 2]',
      '[Page 3, Fig 1 ]',
      // OCR markdown has no page numbers, so the prompt allows page-less markers.
      '[Fig 4b, quote: "2.3 V onset"]',
      '[quote: "88.4% capacity retention"]',
      '[Table 2, box_2d: [1, 2, 3, 4], quote: "500 cycles"]',
    ]) {
      expect(matches(s)).toBe(true)
    }
  })

  test('rejects bare references, links and malformed markers', () => {
    for (const s of [
      '[1]',
      '[Smith 2020]',
      '[Fig 4b]',
      '[x](url)',
      '[, Fig 1]',
      '[Page 1, Fig 1, quote: ""]',
      '[quote: ""]',
    ]) {
      expect(matches(s)).toBe(false)
    }
  })
})

describe('extractCitationMarkers', () => {
  test('swaps markers for indexed placeholders and parses the fields', () => {
    const { text, refs } = extractCitationMarkers(
      'Rises [Page 7, Fig 4b, box_2d: [320, 150, 680, 890], quote: "up 31%"] then [Page 2, Table 1].',
    )
    expect(text).toBe('Rises \uE0010\uE002 then \uE0011\uE002.')
    expect(refs).toEqual([
      { page: 7, label: 'Fig 4b', box: [320, 150, 680, 890], quote: 'up 31%' },
      { page: 2, label: 'Table 1' },
    ])
    expect(text.split(PLACEHOLDER_RE)).toEqual(['Rises ', '0', ' then ', '1', '.'])
  })

  test('parses page-less markers without inventing a page', () => {
    const { text, refs } = extractCitationMarkers(
      'Onset [Fig 4, quote: "2.3 V onset"] and [quote: "88.4% retention"].',
    )
    expect(text).toBe('Onset 0 and 1.')
    expect(refs).toEqual([{ label: 'Fig 4', quote: '2.3 V onset' }, { quote: '88.4% retention' }])
  })

  test('collapses duplicate markers to one ref, like the backend', () => {
    const { text, refs } = extractCitationMarkers('[Page 1, Fig 1] and again [Page 1,  Fig 1 ].')
    expect(refs).toHaveLength(1)
    expect(text).toBe('\uE0010\uE002 and again \uE0010\uE002.')
  })

  test('leaves text without markers untouched', () => {
    const src = 'See [1] and [Smith 2020].'
    expect(extractCitationMarkers(src)).toEqual({ text: src, refs: [] })
  })
})

describe('holdBackOpenMarker', () => {
  test('cuts an unclosed marker, including one open inside the nested box', () => {
    expect(holdBackOpenMarker('Rises [Page 7, Fig 4b, box_2d: [320, 150')).toBe('Rises')
    expect(holdBackOpenMarker('Rises [Page 7, Fig')).toBe('Rises')
    expect(holdBackOpenMarker('Rises [Pa')).toBe('Rises')
  })

  test('keeps closed markers and only cuts the open one', () => {
    const closed = 'A [Page 1, Fig 1] b'
    expect(holdBackOpenMarker(closed)).toBe(closed)
    expect(holdBackOpenMarker('A [Page 1, Fig 1] b [Page 2, Fig')).toBe('A [Page 1, Fig 1] b')
  })

  test('ignores brackets inside the quote', () => {
    const src = 'A [Page 1, Fig 1, quote: "x] y"] z'
    expect(holdBackOpenMarker(src)).toBe(src)
    expect(holdBackOpenMarker('A [Page 1, Fig 1, quote: "x] y')).toBe('A')
  })

  test('is a no-op without markers', () => {
    expect(holdBackOpenMarker('Plain text [1] and [x](y).')).toBe('Plain text [1] and [x](y).')
  })

  test('holds back a page-less marker that has started', () => {
    expect(holdBackOpenMarker('Rises [Fig 4b, quo')).toBe('Rises')
    expect(holdBackOpenMarker('Rises [quote: "up 31')).toBe('Rises')
    expect(holdBackOpenMarker('Rises [')).toBe('Rises')
    const closed = 'Rises [Fig 4b, quote: "up 31%"] then'
    expect(holdBackOpenMarker(closed)).toBe(closed)
  })

  test('leaves a stray open bracket that cannot become a marker', () => {
    const interval = 'on the interval [0, 1) the function is'
    expect(holdBackOpenMarker(interval)).toBe(interval)
    const ranOn = 'see [' + 'a'.repeat(121)
    expect(holdBackOpenMarker(ranOn)).toBe(ranOn)
    const index = 'so `w[i` grows with'
    expect(holdBackOpenMarker(index)).toBe(index)
  })

  test('a stray bracket earlier in the text does not swallow a later marker', () => {
    const prefix = 'Normalised to [0, 1) the onset rises'
    expect(holdBackOpenMarker(`${prefix} [Page 3`)).toBe(prefix)
    expect(holdBackOpenMarker(`${prefix} [Page 3, quote: "2.3 V`)).toBe(prefix)
    const done = `${prefix} [Page 3, quote: "2.3 V"] and stays flat.`
    expect(holdBackOpenMarker(done)).toBe(done)
    const set = 'The set [a, b, c and later [Page 9, quote: "value"] confirm this.'
    expect(holdBackOpenMarker(set)).toBe(set)
  })

  test('prose quotes never hide brackets', () => {
    const src = 'She said "look [here" and then [Page 2, Fig 1] followed.'
    expect(holdBackOpenMarker(src)).toBe(src)
    expect(holdBackOpenMarker('She said "look" then [Page 2, quote: "a')).toBe(
      'She said "look" then',
    )
  })

  test('holds a long label without a length flicker', () => {
    const long = 'See [Extended Data Figure 4b and Supplementary Table 3,'
    expect(holdBackOpenMarker(long)).toBe('See')
  })
})

describe('matchCitations', () => {
  const refs = [
    { page: 7, label: 'Fig 4b', quote: 'a' },
    { page: 2, label: 'Table 1' },
  ]

  test('pairs by position when counts agree', () => {
    const cits = [
      { page: 7, label: 'Fig 4b', verified_in_source: true },
      { page: 2, label: 'Table 1', verified_in_source: false },
    ]
    expect(matchCitations(refs, cits)).toEqual(cits)
  })

  test('falls back to page + label matching, each citation used once', () => {
    const cits = [
      { page: 9, label: 'Fig 9' },
      { page: 2, label: 'Table 1', verified_in_source: true },
      { page: 7, label: 'Fig 4b', quote: 'a', verified_in_source: true },
    ]
    expect(matchCitations(refs, cits)).toEqual([cits[2], cits[1]])
    expect(matchCitations([{ page: 3 }], cits)).toEqual([null])
  })

  test('pairs page-less refs with page-less citations', () => {
    const cits = [
      { page: 2, label: 'Fig 4', verified_in_source: true },
      { page: null, label: 'Fig 4', quote: 'a', verified_in_source: true },
    ]
    expect(matchCitations([{ label: 'Fig 4', quote: 'a' }], cits)).toEqual([cits[1]])
  })
})

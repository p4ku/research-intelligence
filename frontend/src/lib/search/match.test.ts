import { fixturePapers } from '@/lib/bff/papers/fixtures'
import { describe, expect, test } from 'bun:test'
import {
  detectId,
  highlight,
  isQuestion,
  normalize,
  parseQuery,
  rank,
  snippet,
  tokenize,
  type Searchable,
} from './match'

const paper = (over: Partial<Searchable>): Searchable => ({
  title: '',
  authors: [],
  abstract: '',
  arxiv_id: null,
  doi: null,
  signal_score: null,
  ...over,
})

const score = (p: Searchable, q: string) => rank(p, parseQuery(q))?.score ?? null

describe('normalize / tokenize', () => {
  test('strips diacritics, lowercases, and turns dashes into spaces', () => {
    expect(normalize('Café  Müller — Solid-State')).toBe('cafe muller solid state')
  })
  test('drops one-character tokens and punctuation, stems plurals', () => {
    expect(tokenize('AI & robots, a b')).toEqual(['ai', 'robot'])
    expect(tokenize('batteries agents glass')).toEqual(['battery', 'agent', 'glass'])
  })
  test('drops function words unless nothing else is left', () => {
    expect(parseQuery('how do agents coordinate tools').tokens).toEqual([
      'agent',
      'coordinate',
      'tool',
    ])
    expect(parseQuery('what is there').tokens).toEqual(['what', 'is', 'there'])
  })
})

describe('rank', () => {
  const solid = paper({ title: 'Solid-State Batteries for Cold Chains' })

  test('hyphen and space are the same thing', () => {
    expect(score(solid, 'solid state')).toBe(score(solid, 'solid-state'))
    expect(score(solid, 'solid state')).toBeGreaterThan(0)
  })
  test('a joined word hits the hyphenated field form, plurals hit singulars', () => {
    expect(score(paper({ title: 'Multi-Agent Systems' }), 'multiagent')).not.toBeNull()
    expect(score(paper({ title: 'Multi-Agent Systems' }), 'agents')).not.toBeNull()
    expect(score(paper({ title: 'A solid-state battery' }), 'batteries')).not.toBeNull()
  })
  test('every token must land (AND)', () => {
    const [coordinated, survey] = fixturePapers
    const q = parseQuery('agents survey')
    expect(rank(survey!, q)).not.toBeNull()
    expect(rank(coordinated!, q)).toBeNull()
  })
  test('prefixes hit titles freely, abstracts only from four characters', () => {
    // prefix 85 + title start 5 + full title coverage 10 (no phrase bonus for one word)
    expect(score(paper({ title: 'Coordinated Tool Use' }), 'coord')).toBe(100)
    expect(score(paper({ abstract: 'We study agents.' }), 'stu')).toBeNull()
    expect(score(paper({ abstract: 'We study agents.' }), 'stud')).not.toBeNull()
  })
  test('title beats abstract and reports the fields that hit', () => {
    const inTitle = rank(paper({ title: 'Perovskite cells' }), parseQuery('perovskite'))!
    const inAbstract = rank(paper({ abstract: 'On perovskite cells.' }), parseQuery('perovskite'))!
    expect(inTitle.score).toBeGreaterThan(inAbstract.score)
    expect(inTitle.matched).toEqual(['title'])
    expect(inAbstract.matched).toEqual(['abstract'])
  })
  test('the whole query as a phrase in the title earns a bonus', () => {
    const phrase = score(paper({ title: 'Tool Use in Multi-Agent Systems' }), 'tool use')!
    const scattered = score(paper({ title: 'Multi-Agent Tool Systems Use' }), 'tool use')!
    expect(phrase - scattered).toBeGreaterThanOrEqual(15)
  })
  test('signal only breaks ties', () => {
    const strong = paper({ title: 'Cold chain sensing', signal_score: 90 })
    const weak = paper({ title: 'Cold chain sensing', signal_score: 10 })
    expect(score(strong, 'cold chain')!).toBeGreaterThan(score(weak, 'cold chain')!)
    const titleHit = paper({ title: 'Cold chain sensing', signal_score: 0 })
    const abstractHit = paper({ abstract: 'A cold chain study.', signal_score: 100 })
    expect(score(titleHit, 'cold chain')!).toBeGreaterThan(score(abstractHit, 'cold chain')!)
  })
  test('an id fragment matches through the id field', () => {
    const hit = rank(fixturePapers[0]!, parseQuery('2608'))!
    expect(hit.matched).toEqual(['id'])
    expect(hit.score).toBeCloseTo(30 + 87.5 / 1000, 5)
  })
  test('an empty query never matches', () => {
    expect(rank(fixturePapers[0]!, parseQuery('   '))).toBeNull()
  })
})

describe('detectId', () => {
  test('new-style arXiv ids, with or without version or prefix', () => {
    const want = {
      kind: 'arxiv' as const,
      value: '2608.01234',
      url: 'https://arxiv.org/abs/2608.01234',
    }
    expect(detectId('2608.01234v2')).toEqual(want)
    expect(detectId('arXiv:2608.01234')).toEqual(want)
    expect(detectId('https://arxiv.org/pdf/2608.01234v1.pdf')).toEqual(want)
  })
  test('old-style arXiv ids', () => {
    expect(detectId('cs/0301001')?.value).toBe('cs/0301001')
    expect(detectId('hep-th/9901001v1')?.kind).toBe('arxiv')
  })
  test('DOIs, lowercased, with url', () => {
    const want = {
      kind: 'doi' as const,
      value: '10.1000/fixture.42',
      url: 'https://doi.org/10.1000/fixture.42',
    }
    expect(detectId('10.1000/fixture.42')).toEqual(want)
    expect(detectId('doi:10.1000/Fixture.42')).toEqual(want)
    expect(detectId('https://doi.org/10.1000/fixture.42')).toEqual(want)
  })
  test('not ids', () => {
    for (const s of ['2608.1', '10.5 percent', 'arxiv', 'solid state']) {
      expect(detectId(s)).toBeNull()
      expect(parseQuery(s).intent.kind).not.toBe('id')
    }
  })
})

describe('parseQuery intents', () => {
  test('questions in English and German, by opener or by mark', () => {
    for (const q of [
      'what limits solid-state batteries',
      'solid state batteries?',
      'Welche Batterien',
    ]) {
      const parsed = parseQuery(q)
      expect(parsed.intent.kind).toBe('question')
      expect(parsed.tokens.length).toBeGreaterThan(0)
    }
    expect(parseQuery('solid state batteries').intent.kind).toBe('text')
    expect(isQuestion('a b c d e f g', ['ab', 'cd'])).toBe(false)
  })
  test('empty and whitespace', () => {
    expect(parseQuery('').intent).toEqual({ kind: 'empty' })
    expect(parseQuery('   ').tokens).toEqual([])
  })
})

describe('highlight', () => {
  test('keeps the original casing and diacritics', () => {
    expect(highlight('Café Müller', ['muller'])).toEqual([
      { text: 'Café ', hit: false },
      { text: 'Müller', hit: true },
    ])
  })
  test('merges adjacent and overlapping tokens into one segment', () => {
    expect(highlight('Multi-Agent tools', ['multi', 'agent'])).toEqual([
      { text: 'Multi-Agent', hit: true },
      { text: ' tools', hit: false },
    ])
    const overlapping = highlight('multiagent', ['multi', 'multiagent'])
    expect(overlapping).toEqual([{ text: 'multiagent', hit: true }])
  })
  test('extends a prefix hit to the whole word and only opens words', () => {
    expect(highlight('Coordinated Tool Use', ['coord'])).toEqual([
      { text: 'Coordinated', hit: true },
      { text: ' Tool Use', hit: false },
    ])
    expect(highlight('uncoordinated', ['coord'])).toEqual([{ text: 'uncoordinated', hit: false }])
    expect(highlight('Web Agents', tokenize('agent'))).toEqual([
      { text: 'Web ', hit: false },
      { text: 'Agents', hit: true },
    ])
  })
  test('no tokens, no hits', () => {
    expect(highlight('Plain', [])).toEqual([{ text: 'Plain', hit: false }])
  })
})

describe('snippet', () => {
  const long =
    'We study how cooperating language-model agents divide tool use and show a 31% task-completion gain over single-agent baselines on a new benchmark for long-horizon planning tasks.'

  test('centres on the first hit within the length budget', () => {
    const out = snippet(long, ['benchmark'], 60)
    expect(out).toContain('benchmark')
    expect(out.startsWith('…')).toBe(true)
    expect(out.length).toBeLessThanOrEqual(62)
  })
  test('falls back to the head when nothing hits, and leaves short text alone', () => {
    const out = snippet(long, ['zzz'], 60)
    expect(out.startsWith('We study')).toBe(true)
    expect(out.endsWith('…')).toBe(true)
    expect(snippet('Short.', ['short'], 60)).toBe('Short.')
  })
})

import { fixturePapers } from '@/lib/bff/papers/fixtures'
import { assembleSearch } from '@/lib/bff/search/assemble'
import { fixtureSearchCorpus } from '@/lib/bff/search/fixtures'
import type { T } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import { askTitle, buildSections, flatten, papersHref, rowId, type RowContext } from './rows'

const t: T = (s) => s
const ctx = (over: Partial<RowContext> = {}): RowContext => ({
  q: 'agents',
  recent: [],
  suggestions: [],
  error: false,
  t,
  ...over,
})
const search = (q: string, limit = 6) => assembleSearch(fixtureSearchCorpus, { q, limit })
const kinds = (q: string, limit = 6, over: Partial<RowContext> = {}) =>
  flatten(buildSections(search(q, limit), ctx({ q, ...over }))).map((r) => r.kind)

describe('buildSections', () => {
  // The fixture domain is "Agentic AI Scan", so "agents" also matches a domain.
  test('text: papers, domains, then the Ask row last', () => {
    expect(kinds('agents')).toEqual(['paper', 'paper', 'domain', 'ask'])
    const [papers] = buildSections(search('agents'), ctx())
    expect(papers?.label).toBe('Papers')
  })

  test('"See all" only when the limit hid some', () => {
    expect(kinds('agents', 1)).toEqual(['paper', 'more', 'domain', 'ask'])
    const more = flatten(buildSections(search('agents', 1), ctx())).find((r) => r.kind === 'more')
    expect(more && 'href' in more ? more.href : null).toBe('/papers?q=agents')
  })

  test('question: the Ask row first', () => {
    expect(kinds('how do agents coordinate tools')[0]).toBe('ask')
  })

  test('id with an exact hit: one Open paper row, then Ask', () => {
    const sections = buildSections(search('2608.01234'), ctx({ q: '2608.01234' }))
    expect(sections[0]?.key).toBe('exact')
    expect(sections[0]?.label).toBe('Open paper')
    expect(flatten(sections).map((r) => r.kind)).toEqual(['paper', 'ask'])
    expect(flatten(sections)[0]).toMatchObject({ href: `/papers/${fixturePapers[0]!.id}` })
  })

  test('id without a hit: an honest note and Open Papers', () => {
    const sections = buildSections(search('10.9999/nope'), ctx({ q: '10.9999/nope' }))
    expect(sections[0]?.note).toBe('No paper with that id in your corpus.')
    expect(flatten(sections).map((r) => r.kind)).toEqual(['papers'])
  })

  test('no hits: the query named in the note', () => {
    const sections = buildSections(search('perovskite'), ctx({ q: 'perovskite' }))
    expect(sections[0]?.note).toBe('No papers match “perovskite”.')
    expect(flatten(sections).map((r) => r.kind)).toEqual(['papers'])
  })

  test('domains section when the domain name matches', () => {
    expect(kinds('agentic')).toContain('domain')
  })

  test('nothing typed: recent then try, nothing at all when both are empty', () => {
    expect(buildSections(null, ctx({ q: '' }))).toEqual([])
    const sections = buildSections(
      null,
      ctx({ q: '', recent: ['cold chain'], suggestions: ['agentic AI'] }),
    )
    expect(sections.map((s) => s.key)).toEqual(['recent', 'try'])
    expect(flatten(sections).map((r) => r.kind)).toEqual(['recent', 'try'])
  })

  test('typing with no result yet shows nothing; an outage says so', () => {
    expect(buildSections(null, ctx({ q: 'ag' }))).toEqual([])
    const down = buildSections(null, ctx({ q: 'agents', error: true }))
    expect(down[0]?.note).toBe('Search is unavailable — press Enter to open Papers.')
    expect(flatten(down).map((r) => r.kind)).toEqual(['papers'])
    // With stale results the note sits above them.
    const stale = buildSections(search('agents'), ctx({ error: true }))
    expect(stale[0]?.key).toBe('note')
    expect(flatten(stale).map((r) => r.kind)).toEqual(['paper', 'paper', 'domain', 'ask'])
  })

  test('a suggestion already in Recent is not offered twice', () => {
    const sections = buildSections(
      null,
      ctx({ q: '', recent: ['Machine Learning'], suggestions: ['machine learning', 'RFID'] }),
    )
    expect(
      flatten(sections)
        .map((r) => (r.kind === 'try' ? r.q : null))
        .filter(Boolean),
    ).toEqual(['RFID'])
  })

  test('the Ask label keeps a title to one row', () => {
    expect(askTitle('OMLT: Optimization & Machine Learning Toolkit')).toBe('OMLT')
    const long =
      'A Quantum-Classical Hybrid Framework for Multivariate Time-Series Forecasting and More'
    const clipped = askTitle(long)
    expect(clipped.length).toBeLessThanOrEqual(61)
    expect(clipped.endsWith('…')).toBe(true)
    expect(clipped).toBe('A Quantum-Classical Hybrid Framework for Multivariate…')
  })

  test('row ids are stable and unique; papersHref encodes', () => {
    const ids = flatten(buildSections(search('agents'), ctx())).map(rowId)
    expect(new Set(ids).size).toBe(ids.length)
    expect(papersHref(' solid state ')).toBe('/papers?q=solid%20state')
    expect(papersHref('')).toBe('/papers')
  })
})

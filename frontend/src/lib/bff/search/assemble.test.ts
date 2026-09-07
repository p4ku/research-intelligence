import { describe, expect, test } from 'bun:test'
import { fixturePapers, fixtureWorkspace } from '../papers/fixtures'
import { assembleSearch, type SearchCorpus } from './assemble'
import { fixtureSearchCorpus } from './fixtures'
import { searchQuery, searchResponse } from './schema'

const [coordinated, survey] = fixturePapers as [
  (typeof fixturePapers)[number],
  (typeof fixturePapers)[number],
]
const run = (q: string, limit = 8, corpus: SearchCorpus = fixtureSearchCorpus) =>
  assembleSearch(corpus, { q, limit })

describe('assembleSearch', () => {
  test('text: ranked hits, total, hidden-by-screening, domain name, snippet', () => {
    const r = run('agents')
    expect(r.intent).toBe('text')
    expect(r.papers_total).toBe(2)
    expect(r.papers[0]?.id).toBe(coordinated.id)
    expect(r.papers[0]?.signal_score).toBe(87.5)
    expect(r.papers[0]?.workspace_name).toBe(fixtureWorkspace.name)
    expect(r.papers[0]?.snippet.toLowerCase()).toContain('agents')
    expect(r.papers_hidden_by_screening).toBe(1)
    expect(r.ask?.paper_id).toBe(coordinated.id)
    expect(r.ask?.href).toBe(`/ask?q=agents&paper=${coordinated.id}`)
  })

  test('limit truncates rows but not the total', () => {
    const r = run('agents', 1)
    expect(r.papers).toHaveLength(1)
    expect(r.papers_total).toBe(2)
  })

  test('a passed paper wins a near-tie against a rejected one', () => {
    const corpus: SearchCorpus = {
      ...fixtureSearchCorpus,
      papers: [
        { ...survey, id: '00000000-0000-4000-8000-000000000099', title: 'Cold chain sensing' },
        { ...coordinated, title: 'Cold chain sensing', signal_score: 0 },
      ],
    }
    const r = run('cold chain', 8, corpus)
    expect(r.papers[0]?.id).toBe(coordinated.id)
  })

  test('id: an arXiv id resolves to the exact paper, ask scoped to it', () => {
    const r = run('2608.01234v1')
    expect(r.intent).toBe('id')
    expect(r.exact).toEqual({ paper_id: coordinated.id })
    expect(r.id).toEqual({
      kind: 'arxiv',
      value: '2608.01234',
      url: 'https://arxiv.org/abs/2608.01234',
    })
    expect(r.papers).toHaveLength(1)
    expect(r.domains).toEqual([])
    expect(r.ask?.paper_id).toBe(coordinated.id)
  })

  test('id: a DOI hit and an honest miss', () => {
    expect(run('10.1000/Fixture.42').exact).toEqual({ paper_id: survey.id })
    const miss = run('10.9999/nope')
    expect(miss.intent).toBe('id')
    expect(miss.exact).toBeNull()
    expect(miss.papers).toEqual([])
    expect(miss.id?.kind).toBe('doi')
    expect(miss.ask).toBeNull()
  })

  test('question: intent flips, ask still scoped to the top hit', () => {
    const r = run('how do agents coordinate tools')
    expect(r.intent).toBe('question')
    expect(r.ask?.href).toBe(
      `/ask?q=how%20do%20agents%20coordinate%20tools&paper=${coordinated.id}`,
    )
  })

  test('no hits: nothing to ask about', () => {
    const r = run('perovskite')
    expect(r.papers_total).toBe(0)
    expect(r.ask).toBeNull()
  })

  test('domains: name match with and without an edition', () => {
    const word = fixtureWorkspace.name.split(' ')[0]!
    const withEdition = run(word)
    expect(withEdition.domains).toHaveLength(1)
    expect(withEdition.domains[0]?.latest_edition?.href).toBe(
      `/briefing/${fixtureSearchCorpus.latestEdition[fixtureWorkspace.id]}?domain=${fixtureWorkspace.id}`,
    )
    const without = run(word, 8, { ...fixtureSearchCorpus, latestEdition: {} })
    expect(without.domains[0]?.latest_edition).toBeNull()
  })

  test('empty query is an empty response', () => {
    const r = run('')
    expect(r.intent).toBe('empty')
    expect(r.papers).toEqual([])
  })

  test('every response parses against the contract', () => {
    for (const q of ['', 'agents', '2608.01234', '10.9999/nope', 'what is new?', 'Agentic']) {
      const parsed = searchResponse.safeParse(run(q))
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
  })
})

describe('searchQuery', () => {
  test('defaults, caps and coercion', () => {
    expect(searchQuery.parse({})).toEqual({ q: '', limit: 8 })
    expect(searchQuery.parse({ q: '  agents ', limit: '12' })).toEqual({ q: 'agents', limit: 12 })
    expect(searchQuery.parse({ limit: '50' }).limit).toBe(8)
    expect(searchQuery.safeParse({ q: 'x'.repeat(201) }).success).toBe(false)
  })
})

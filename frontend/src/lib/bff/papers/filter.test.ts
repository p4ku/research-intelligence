import type { ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { applyPapersQuery, corpusFacets, orderRows } from './filter'
import { fixturePapers, fixtureWorkspace } from './fixtures'
import { papersQuery, type PapersQuery } from './schema'

const base = fixturePapers[0]!
const id = (n: number) => `00000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`
const day = (n: number) => `2026-08-${String(n).padStart(2, '0')}T06:00:00Z`

function trl(value: number | null) {
  return {
    key: 'trl_level',
    definition_id: fixtureWorkspace.definitions[2]!.id,
    name: 'TRL Level',
    value,
    raw: value === null ? '' : String(value),
    max: 9,
    is_trl: true,
  }
}

/** Five papers with distinct titles, scores, dates and TRLs; two rejected. */
function corpus(): { workspaces: (typeof fixtureWorkspace)[]; papers: ScoredPaper[] } {
  const plain = {
    ...base,
    abstract: '',
    authors: [] as string[],
    dimensions: [] as ScoredPaper['dimensions'],
  }
  return {
    workspaces: [fixtureWorkspace],
    papers: [
      {
        ...plain,
        id: id(1),
        title: 'Multi-Agent Planning',
        signal_score: 90,
        created_at: day(30),
        screening_status: 'accepted',
        dimensions: [trl(3)],
      },
      {
        ...plain,
        id: id(2),
        title: 'Battery Chemistry',
        signal_score: 70,
        created_at: day(20),
        screening_status: 'full_text_passed',
        dimensions: [trl(8)],
      },
      {
        ...plain,
        id: id(3),
        title: 'Agents That Negotiate',
        signal_score: 50,
        created_at: day(10),
        screening_status: 'rejected',
        dimensions: [trl(5)],
      },
      {
        ...plain,
        id: id(4),
        title: 'Solid State Electrolytes',
        signal_score: null,
        created_at: day(1),
        screening_status: 'abstract_passed',
        dimensions: [trl(null)],
      },
      {
        ...plain,
        id: id(5),
        title: 'Agent Benchmarks',
        signal_score: 20,
        created_at: day(25),
        screening_status: 'rejected',
      },
    ],
  }
}

// The page sends screening=passed explicitly; the HTTP face's own default is 'all'.
const q = (overrides: Partial<PapersQuery> = {}): PapersQuery => ({
  ...papersQuery.parse({}),
  screening: 'passed',
  ...overrides,
})
const novelty = (value: number | null) => ({
  key: 'novelty_score',
  definition_id: fixtureWorkspace.definitions[1]!.id,
  name: 'Novelty Score',
  value,
  raw: value === null ? '' : String(value),
  max: 10,
  is_trl: false,
})
const none = new Set<string>()
const ids = (rows: ScoredPaper[]) => rows.map((r) => r.id)

describe('applyPapersQuery', () => {
  test('the default query is the passed papers by signal, unscored last', () => {
    const { rows, hiddenByScreening } = applyPapersQuery(corpus(), q(), none)
    expect(ids(rows)).toEqual([id(1), id(2), id(4)])
    expect(hiddenByScreening).toBe(0)
  })

  test('screening: all, and an exact status', () => {
    expect(ids(applyPapersQuery(corpus(), q({ screening: 'all' }), none).rows)).toHaveLength(5)
    expect(ids(applyPapersQuery(corpus(), q({ screening: 'rejected' }), none).rows)).toEqual([
      id(3),
      id(5),
    ])
  })

  test('a domain narrows; a foreign one empties', () => {
    expect(
      applyPapersQuery(corpus(), q({ workspace_id: fixtureWorkspace.id }), none).rows,
    ).toHaveLength(3)
    expect(applyPapersQuery(corpus(), q({ workspace_id: id(99) }), none).rows).toHaveLength(0)
  })

  test('starred keeps only the starred ids', () => {
    const { rows } = applyPapersQuery(corpus(), q({ starred: '1' }), new Set([id(2), id(3)]))
    expect(ids(rows)).toEqual([id(2)])
  })

  test('minimum score drops unscored papers too', () => {
    expect(ids(applyPapersQuery(corpus(), q({ min_score: 80 }), none).rows)).toEqual([id(1)])
  })

  test('the TRL window applies, and drops papers without a TRL', () => {
    const { rows } = applyPapersQuery(
      corpus(),
      q({ screening: 'all', min_trl: 4, max_trl: 8 }),
      none,
    )
    expect(ids(rows)).toEqual([id(2), id(3)])
  })

  test('the TRL window is ignored when no paper has a TRL', () => {
    const c = corpus()
    c.papers = c.papers.map((p) => ({ ...p, dimensions: [] }))
    expect(applyPapersQuery(c, q({ min_trl: 4, max_trl: 8 }), none).rows).toHaveLength(3)
  })

  test('the ingested window counts back from the newest paper, not the wall clock', () => {
    // Every date is years old; "last 7 days" still means the freshest drop.
    const { rows } = applyPapersQuery(corpus(), q({ screening: 'all', within_days: 7 }), none)
    expect(ids(rows)).toEqual([id(1), id(5)])
  })

  test('a search narrows to hits and reorders by relevance under the default sort', () => {
    const { rows, hiddenByScreening } = applyPapersQuery(corpus(), q({ search: 'agents' }), none)
    // Passed hits only; the exact plural beats the prefix and the hyphenated form.
    expect(ids(rows)).toEqual([id(1)])
    expect(hiddenByScreening).toBe(2)
  })

  test('an explicit sort filters by search but keeps its own order', () => {
    const { rows } = applyPapersQuery(
      corpus(),
      q({ search: 'agents', screening: 'all', ordering: '-created_at' }),
      none,
    )
    expect(ids(rows)).toEqual([id(1), id(5), id(3)])
  })

  test('sorting by a dimension puts missing values last, both ways', () => {
    const { rows } = applyPapersQuery(
      corpus(),
      q({ screening: 'all', ordering: '-dim:trl_level' }),
      none,
    )
    expect(ids(rows)).toEqual([id(2), id(3), id(1), id(4), id(5)])
    const asc = applyPapersQuery(corpus(), q({ screening: 'all', ordering: 'dim:trl_level' }), none)
    expect(ids(asc.rows)).toEqual([id(1), id(3), id(2), id(4), id(5)])
  })
})

describe('orderRows', () => {
  test('created_at both ways', () => {
    const { papers } = corpus()
    expect(ids(orderRows(papers, '-created_at'))).toEqual([id(1), id(5), id(2), id(3), id(4)])
    expect(ids(orderRows(papers, 'created_at'))).toEqual([id(4), id(3), id(2), id(5), id(1)])
  })
})

describe('corpusFacets', () => {
  test('describes the corpus for the rail', () => {
    // The composer writes one dimension per definition; a paper carrying none
    // at all reads as "unknown", so both non-TRL definitions stay sortable.
    const facets = corpusFacets(corpus(), new Set([id(1), id(99)]))
    expect(facets).toEqual({
      total: 5,
      score_ceiling: 100,
      newest: day(30),
      has_trl: true,
      dimension_sorts: [
        { key: 'fit_score', name: 'Fit Score' },
        { key: 'novelty_score', name: 'Novelty Score' },
      ],
      starred_count: 1,
    })
  })

  test('the ceiling rises with a formula that scores past 100, ceiled', () => {
    const c = corpus()
    c.papers[0] = { ...c.papers[0]!, signal_score: 140.2 }
    expect(corpusFacets(c, none).score_ceiling).toBe(141)
  })

  test('dimension sorts list a definition once across domains, only with a value, never TRL', () => {
    const c = corpus()
    const fit = base.dimensions.find((d) => d.key === 'fit_score')!
    c.papers = c.papers.map((p) => ({ ...p, dimensions: [novelty(null), ...p.dimensions] }))
    c.papers[0] = { ...c.papers[0]!, dimensions: [fit, novelty(null), trl(3)] }
    c.workspaces = [fixtureWorkspace, { ...fixtureWorkspace, id: id(50) }]
    expect(corpusFacets(c, none).dimension_sorts).toEqual([{ key: 'fit_score', name: 'Fit Score' }])
  })

  test('an empty corpus', () => {
    expect(corpusFacets({ workspaces: [], papers: [] }, none)).toEqual({
      total: 0,
      score_ceiling: 100,
      newest: null,
      has_trl: false,
      dimension_sorts: [],
      starred_count: 0,
    })
  })
})

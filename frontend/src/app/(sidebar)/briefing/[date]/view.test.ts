import { fixturePapers } from '@/lib/bff/papers/fixtures'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import {
  applyView,
  DEFAULT_VIEW,
  isDefaultView,
  PAGE_SIZE,
  pageOf,
  searchWith,
  sortOptions,
  viewFrom,
  withKnownSort,
} from './view'

const t = (s: string) => s

function dim(key: string, value: number | null, extra: Partial<Dimension> = {}): Dimension {
  return {
    key,
    definition_id: null,
    name: key,
    value,
    raw: value === null ? null : String(value),
    max: 100,
    is_trl: false,
    ...extra,
  }
}

function paper(
  id: string,
  signal: number | null,
  published: string | null,
  dimensions: Dimension[] = [],
): ScoredPaper {
  return { ...fixturePapers[0]!, id, signal_score: signal, published_date: published, dimensions }
}

const a = paper('a', 70, '2026-09-01', [
  dim('rigour', 40, { order: 1 }),
  dim('trl', 3, { is_trl: true, order: 0 }),
])
const b = paper('b', 90, null, [dim('rigour', 80, { order: 1 })])
const c = paper('c', null, '2026-09-05', [dim('rigour', null, { order: 1 })])
const d = paper('d', 90, '2026-08-20', [
  dim('risk_and_affiliation', 5, { is_risk_and_affiliation: true }),
])

describe('viewFrom', () => {
  test('defaults on a bare permalink and on junk', () => {
    expect(viewFrom({})).toEqual(DEFAULT_VIEW)
    expect(viewFrom({ sort: 'dim:', score: '-5' })).toEqual(DEFAULT_VIEW)
    expect(viewFrom({ score: '57.5' })).toEqual(DEFAULT_VIEW)
    expect(viewFrom({ score: '0' })).toEqual(DEFAULT_VIEW)
    expect(viewFrom({ score: '500' })).toEqual(DEFAULT_VIEW)
    expect(isDefaultView(viewFrom({}))).toBe(true)
  })

  test('reads a sort and a score floor, first value of a repeated param', () => {
    // One point a step (10 Sep 2026): a floor of 57 is the slider's own.
    expect(viewFrom({ score: '57' })).toEqual({ sort: 'score', minScore: 57, page: 1 })
    expect(viewFrom({ sort: ['published', 'score'], score: '60' })).toEqual({
      sort: 'published',
      minScore: 60,
      page: 1,
    })
    expect(viewFrom({ sort: 'dim:rigour' }).sort).toBe('dim:rigour')
    expect(viewFrom({ sort: 'dim:technology_readiness_level_(trl)' }).sort).toBe(
      'dim:technology_readiness_level_(trl)',
    )
    expect(viewFrom({ sort: 'dim:a b' })).toEqual(DEFAULT_VIEW)
  })

  test('reads dynamic dimension filters and marks view as non-default', () => {
    const view = viewFrom({ min_trl: '6', 'dim:schwarz_fit': '8', min_score: '50' })
    expect(view).toEqual({
      sort: 'score',
      minScore: 0,
      page: 1,
      dimensionFilters: {
        trl: 6,
        schwarz_fit: 8,
      },
    })
    expect(isDefaultView(view)).toBe(false)
  })
})

describe('searchWith', () => {
  test("keeps the briefing's own params and drops defaults", () => {
    expect(searchWith('domain=ws1&run=r1', DEFAULT_VIEW)).toBe('?domain=ws1&run=r1')
    expect(searchWith('domain=ws1&sort=published&score=40', DEFAULT_VIEW)).toBe('?domain=ws1')
    expect(searchWith('', DEFAULT_VIEW)).toBe('')
  })

  test('writes the view beside them', () => {
    expect(searchWith('run=r1', { sort: 'dim:rigour', minScore: 55, page: 1 })).toBe(
      '?run=r1&sort=dim%3Arigour&score=55',
    )
  })

  test('writes dynamic dimension filters and strips zero values', () => {
    expect(
      searchWith('run=r1', {
        sort: 'score',
        minScore: 0,
        page: 1,
        dimensionFilters: { trl: 6, schwarz_fit: 8 },
      }),
    ).toBe('?run=r1&min_trl=6&min_schwarz_fit=8')

    expect(
      searchWith('run=r1&min_trl=6', {
        sort: 'score',
        minScore: 0,
        page: 1,
        dimensionFilters: { trl: 0 },
      }),
    ).toBe('?run=r1')
  })
})

describe('sortOptions', () => {
  test('score and date first, then each scored dimension once in definition order, TRL included', () => {
    expect(sortOptions([a, b, c, d], t)).toEqual([
      { id: 'score', label: 'Total Score' },
      { id: 'published', label: 'Date published' },
      { id: 'dim:trl', label: 'TRL' },
      { id: 'dim:rigour', label: 'Rigour' },
    ])
  })

  test('the date is offered only when some paper carries one', () => {
    const undated = [b, paper('e', 40, null, [dim('rigour', 10, { order: 1 })])]
    expect(sortOptions(undated, t).map((s) => s.id)).toEqual(['score', 'dim:rigour'])
    expect(sortOptions([...undated, c], t).map((s) => s.id)).toContain('published')
  })

  test('a dimension nobody scored, and the affiliation flags, are not offered', () => {
    expect(sortOptions([c, d], t).map((s) => s.id)).toEqual(['score', 'published'])
  })

  test('uses definitions metadata when provided, even if papers list is empty', () => {
    const definitions = [
      { key: 'trl', name: 'Technology Readiness Level (TRL)', order: 1, is_trl: true },
      { key: 'schwarz_fit', name: 'Schwarz Fit', order: 2 },
      { key: 'risk_and_affiliation', name: 'Risk & Affiliation', order: 3 },
    ]
    expect(sortOptions([], t, definitions)).toEqual([
      { id: 'score', label: 'Total Score' },
      { id: 'dim:trl', label: 'TRL' },
      { id: 'dim:schwarz_fit', label: 'Schwarz Fit' },
    ])
  })
})

describe('applyView', () => {
  const ids = (ps: ScoredPaper[]) => ps.map((p) => p.id)

  test('default: by score, ties in the briefing order, unscored last', () => {
    expect(ids(applyView([a, b, c, d], DEFAULT_VIEW))).toEqual(['b', 'd', 'a', 'c'])
  })

  test('by publication date, newest first, undated last', () => {
    expect(ids(applyView([a, b, c, d], { sort: 'published', minScore: 0, page: 1 }))).toEqual([
      'c',
      'a',
      'd',
      'b',
    ])
  })

  test('by a dimension, nulls and papers without it last', () => {
    expect(ids(applyView([a, b, c, d], { sort: 'dim:rigour', minScore: 0, page: 1 }))).toEqual([
      'b',
      'a',
      'c',
      'd',
    ])
  })

  test('the floor keeps scores at or above it and drops the unscored', () => {
    expect(ids(applyView([a, b, c, d], { sort: 'score', minScore: 70, page: 1 }))).toEqual([
      'b',
      'd',
      'a',
    ])
    expect(ids(applyView([a, b, c, d], { sort: 'score', minScore: 75, page: 1 }))).toEqual([
      'b',
      'd',
    ])
  })

  test('the floor and the order read the exact score, not the whole number the card prints', () => {
    // Both print "75"; only the one stored at or above 75 clears the floor,
    // and the higher of the two leads the list.
    const just = paper('just', 74.6, null, [])
    const over = paper('over', 75.4, null, [])
    expect(ids(applyView([just, over], { sort: 'score', minScore: 75, page: 1 }))).toEqual(['over'])
    expect(ids(applyView([just, over], { sort: 'score', minScore: 0, page: 1 }))).toEqual([
      'over',
      'just',
    ])
  })

  test('filters by dynamic dimension floors in applyView', () => {
    // a has rigour: 40, trl: 3
    // b has rigour: 80, no trl
    // c has rigour: null
    // d has no rigour
    expect(
      ids(
        applyView([a, b, c, d], {
          sort: 'score',
          minScore: 0,
          page: 1,
          dimensionFilters: { rigour: 50 },
        }),
      ),
    ).toEqual(['b'])

    expect(
      ids(
        applyView([a, b, c, d], {
          sort: 'score',
          minScore: 0,
          page: 1,
          dimensionFilters: { rigour: 30, trl: 2 },
        }),
      ),
    ).toEqual(['a'])
  })

  test('does not reorder the input', () => {
    const input = [a, b, c]
    applyView(input, DEFAULT_VIEW)
    expect(ids(input)).toEqual(['a', 'b', 'c'])
  })
})

describe('review follow-ups', () => {
  const ids = (ps: ScoredPaper[]) => ps.map((p) => p.id)

  test('every key the rail offers reads back from the URL', () => {
    const odd = paper('odd', 60, null, [
      dim('sovereign_cloud_&_commercial_viability', 70, { order: 0 }),
      dim('cost/benefit', 50, { order: 1 }),
      dim('marktreife_für_europa', 40, { order: 2 }),
      dim("founder's_fit", 30, { order: 3 }),
    ])
    const offered = sortOptions([odd], t).map((o) => o.id)
    expect(offered).toHaveLength(5)
    for (const id of offered) expect(viewFrom({ sort: id }).sort).toBe(id)
  })

  test('a sort the papers cannot honour falls back to the score, keeping the floor', () => {
    const options = sortOptions([a, b], t)
    expect(withKnownSort({ sort: 'dim:nope', minScore: 10, page: 1 }, options)).toEqual({
      sort: 'score',
      minScore: 10,
      page: 1,
    })
    expect(withKnownSort({ sort: 'dim:rigour', minScore: 0, page: 1 }, options).sort).toBe(
      'dim:rigour',
    )
  })

  test('a missing publication date sorts like no date, whatever the input order', () => {
    const u = { ...paper('u', 50, null), published_date: undefined } as unknown as ScoredPaper
    const view = { sort: 'published', minScore: 0, page: 1 }
    expect(ids(applyView([u, c, a], view))).toEqual(['c', 'a', 'u'])
    expect(ids(applyView([a, c, u], view))).toEqual(['c', 'a', 'u'])
  })
})

describe('page in the view', () => {
  test('viewFrom reads a positive integer page and defaults anything else to 1', () => {
    expect(viewFrom({ page: '3' }).page).toBe(3)
    expect(viewFrom({}).page).toBe(1)
    expect(viewFrom({ page: '0' }).page).toBe(1)
    expect(viewFrom({ page: '-2' }).page).toBe(1)
    expect(viewFrom({ page: '2.5' }).page).toBe(1)
    expect(viewFrom({ page: 'two' }).page).toBe(1)
    expect(viewFrom({ page: ['4', '9'] }).page).toBe(4)
  })

  test('searchWith writes the page past the first and drops it on the first', () => {
    expect(searchWith('domain=w&run=r', { ...DEFAULT_VIEW, page: 3 })).toBe(
      '?domain=w&run=r&page=3',
    )
    expect(searchWith('domain=w&page=3', { ...DEFAULT_VIEW, page: 1 })).toBe('?domain=w')
    expect(searchWith('page=2', DEFAULT_VIEW)).toBe('')
  })

  test('the page is not a filter: page three of the default view is still the default', () => {
    expect(isDefaultView({ ...DEFAULT_VIEW, page: 3 })).toBe(true)
  })
})

describe('pageOf', () => {
  const rows = Array.from({ length: 45 }, (_, i) => i + 1)

  test('cuts PAGE_SIZE rows per page and reports the range shown', () => {
    expect(PAGE_SIZE).toBe(20)
    const first = pageOf(rows, 1)
    expect(first.rows).toEqual(rows.slice(0, 20))
    expect(first).toMatchObject({ page: 1, pageCount: 3, from: 1, to: 20 })
    const last = pageOf(rows, 3)
    expect(last.rows).toEqual([41, 42, 43, 44, 45])
    expect(last).toMatchObject({ page: 3, pageCount: 3, from: 41, to: 45 })
  })

  test('a page past the end folds back onto the last; below one onto the first', () => {
    expect(pageOf(rows, 9)).toMatchObject({ page: 3, from: 41, to: 45 })
    expect(pageOf(rows, 0)).toMatchObject({ page: 1, from: 1, to: 20 })
  })

  test('a list that fits is one page, and an empty list is one empty page', () => {
    expect(pageOf(rows.slice(0, 20), 2)).toMatchObject({ page: 1, pageCount: 1, from: 1, to: 20 })
    expect(pageOf([], 4)).toEqual({ rows: [], page: 1, pageCount: 1, from: 0, to: 0 })
  })
})

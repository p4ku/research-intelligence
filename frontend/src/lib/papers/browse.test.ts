import { describe, expect, test } from 'bun:test'
import {
  DEFAULT_STATE,
  keyOf,
  listPath,
  PER_PAGE,
  searchOf,
  stateFrom,
  toPapersQuery,
} from './browse'

const WS = '00000000-0000-4000-8000-000000000001'
const domains = [{ id: WS }]

describe('stateFrom / searchOf', () => {
  test('no params is the default state, and the default state is a clean URL', () => {
    expect(stateFrom({}, domains)).toEqual(DEFAULT_STATE)
    expect(searchOf(DEFAULT_STATE)).toBe('')
  })

  test('every control round-trips', () => {
    const state = {
      q: 'agents',
      domain: WS,
      starred: true,
      screening: 'all' as const,
      sort: 'dim:novelty_score',
      minTrl: 3,
      maxTrl: 7,
      withinDays: 30,
      minScore: 40,
      page: 3,
    }
    const url = searchOf(state)
    expect(url).toContain('trl=3-7')
    expect(stateFrom(Object.fromEntries(new URLSearchParams(url)), domains)).toEqual(state)
  })

  test("Home's ?q= hands over and is trimmed", () => {
    expect(stateFrom({ q: '  battery ' }, domains).q).toBe('battery')
  })

  test('unusable values take their defaults', () => {
    const state = stateFrom(
      {
        domain: 'not-a-membership',
        screening: 'nonsense',
        sort: 'dim:Bad Key',
        trl: '7-3',
        days: 'soon',
        score: '-5',
        page: '0',
        starred: 'yes',
      },
      domains,
    )
    expect(state).toEqual(DEFAULT_STATE)
  })

  test('a repeated param reads its first value', () => {
    expect(stateFrom({ page: ['2', '9'] }, domains).page).toBe(2)
  })
})

describe('toPapersQuery', () => {
  test('maps the page vocabulary to the list vocabulary', () => {
    expect(toPapersQuery(DEFAULT_STATE)).toEqual({
      page: 1,
      page_size: PER_PAGE,
      screening: 'passed',
      ordering: '-signal_score',
      search: undefined,
      workspace_id: undefined,
      starred: '0',
      min_score: 0,
      min_trl: 1,
      max_trl: 9,
      within_days: 0,
    })
    expect(toPapersQuery({ ...DEFAULT_STATE, sort: 'recent' }).ordering).toBe('-created_at')
    expect(toPapersQuery({ ...DEFAULT_STATE, sort: 'dim:fit_score' }).ordering).toBe(
      '-dim:fit_score',
    )
    expect(toPapersQuery({ ...DEFAULT_STATE, q: 'x', domain: WS, starred: true })).toMatchObject({
      search: 'x',
      workspace_id: WS,
      starred: '1',
    })
  })

  test('the list path carries every set value and keys equal states equally', () => {
    const a = { ...DEFAULT_STATE, q: 'agents', page: 2 }
    expect(listPath(a)).toBe(
      `/bff/papers?page=2&page_size=${PER_PAGE}&screening=passed&ordering=-signal_score&search=agents&starred=0&min_score=0&min_trl=1&max_trl=9&within_days=0`,
    )
    expect(keyOf(a)).toBe(keyOf({ ...a }))
    expect(keyOf(a)).not.toBe(keyOf({ ...a, page: 3 }))
  })
})

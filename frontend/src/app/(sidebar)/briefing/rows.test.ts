import { fixtureEditions } from '@/lib/bff/briefings/fixtures'
import { fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { fixtureRuns } from '@/lib/bff/pipeline-runs/fixtures'
import type { T } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import {
  composeRows,
  currentRunId,
  filterRows,
  paginate,
  PER_PAGE,
  searchOf,
  stateFrom,
  type ArchiveRow,
} from './rows'

const t: T = (s) => s
const edition = fixtureEditions[0]
// The fixtures do not share an id as shipped; the archive joins on it.
const run = { ...fixtureRuns[0], id: edition.run_id }
const domains = { [fixtureWorkspace.id]: fixtureWorkspace.name }
const older = {
  ...edition,
  run_id: '00000000-0000-4000-8000-000000000032',
  date: '2026-08-20',
  generated_at: '2026-08-20T06:00:00Z',
}

describe('composeRows', () => {
  test('joins an edition to its run for the period and the counters', () => {
    const [row] = composeRows({ editions: [edition], runs: [run], domains, t, lang: 'en' })
    expect(row.id).toBe(edition.run_id)
    expect(row.domain).toBe(fixtureWorkspace.name)
    expect(row.period).toBe('1–31 Aug 2026')
    expect(row.generated).toBe('31 Aug 2026')
    expect(row.screened).toBe(run.total_papers_fetched)
    expect(row.included).toBe(run.total_papers_passed_screening)
    expect(row.current).toBe(true)
    expect(row.brief.href).toBe(`/briefing/${edition.date}?domain=${edition.workspace_id}`)
    expect(row.brief.top).toHaveLength(1)
  })

  test('an edition without a run falls back to its own day and funnel', () => {
    const [row] = composeRows({ editions: [older], runs: [], domains, t, lang: 'en' })
    expect(row.period).toBe('20 Aug 2026')
    expect(row.generated).toBe('20 Aug 2026')
    expect(row.screened).toBe(older.funnel.fetched)
    expect(row.included).toBe(older.funnel.passed_screening)
    expect(row.current).toBe(false)
  })

  test('a run that briefed nothing is not a row', () => {
    const emptyRun = { ...run, total_papers_passed_screening: 0 }
    expect(composeRows({ editions: [edition], runs: [emptyRun], domains, t, lang: 'en' })).toEqual(
      [],
    )
    const bare = { ...older, funnel: { ...older.funnel, passed_screening: 0 } }
    expect(composeRows({ editions: [bare], runs: [], domains, t, lang: 'en' })).toEqual([])
  })

  test('a run whose edition holds none of the papers it passed is not a row either', () => {
    // The counters promise 25; the edition would open onto nothing.
    const unfilled = { ...edition, papers: [], funnel: { ...edition.funnel, surfaced: 0 } }
    expect(composeRows({ editions: [unfilled], runs: [run], domains, t, lang: 'en' })).toEqual([])
  })

  test('only the newest completed run is current', () => {
    const olderRun = {
      ...run,
      id: older.run_id,
      run_date: '2026-08-20',
      started_at: '2026-08-20T05:00:00Z',
      completed_at: '2026-08-20T06:00:00Z',
    }
    const rows = composeRows({
      editions: [edition, older],
      runs: [olderRun, run],
      domains,
      t,
      lang: 'en',
    })
    expect(rows.map((r) => r.current)).toEqual([true, false])
  })
})

describe('currentRunId', () => {
  test('ignores runs that did not complete', () => {
    // The fixtures: one completed, one failed, one running (newest).
    expect(currentRunId(fixtureRuns)).toBe(fixtureRuns[0].id)
    expect(currentRunId([])).toBeNull()
  })
})

function row(id: string, workspaceId: string): ArchiveRow {
  return {
    id,
    workspaceId,
    domain: 'x',
    current: false,
    period: '',
    generated: '',
    screened: 0,
    included: 0,
    brief: { href: '', inBrief: '', screened: 0, included: 0, top: [] },
  }
}

describe('filterRows', () => {
  const rows = [row('a', 'w1'), row('b', 'w2'), row('c', 'w1')]

  test('by domain', () => {
    expect(filterRows(rows, { domain: 'w1', starred: false }, new Set()).map((r) => r.id)).toEqual([
      'a',
      'c',
    ])
  })

  test('by star, and both together', () => {
    const starred = new Set(['b', 'c'])
    expect(filterRows(rows, { domain: null, starred: true }, starred).map((r) => r.id)).toEqual([
      'b',
      'c',
    ])
    expect(filterRows(rows, { domain: 'w1', starred: true }, starred).map((r) => r.id)).toEqual([
      'c',
    ])
  })
})

describe('paginate', () => {
  const items = Array.from({ length: 25 }, (_, i) => i)

  test('twenty per page', () => {
    expect(paginate(items, 1)).toMatchObject({ page: 1, pageCount: 2 })
    expect(paginate(items, 1).items).toHaveLength(PER_PAGE)
    expect(paginate(items, 2).items).toEqual([20, 21, 22, 23, 24])
  })

  test('clamps a stale page into range', () => {
    expect(paginate(items, 99).page).toBe(2)
    expect(paginate(items, 0).page).toBe(1)
    expect(paginate([], 3)).toEqual({ items: [], page: 1, pageCount: 1 })
  })
})

describe('stateFrom', () => {
  const all = [fixtureWorkspace]

  test('keeps a member domain, drops anything else', () => {
    expect(stateFrom({ domain: fixtureWorkspace.id }, all).domain).toBe(fixtureWorkspace.id)
    expect(stateFrom({ domain: '00000000-0000-4000-8000-0000000000ff' }, all).domain).toBeNull()
    expect(stateFrom({ domain: 'nope' }, all).domain).toBeNull()
  })

  test('starred and page', () => {
    expect(stateFrom({ starred: '1', page: '3' }, all)).toMatchObject({ starred: true, page: 3 })
    expect(stateFrom({ starred: 'true', page: 'x' }, all)).toMatchObject({
      starred: false,
      page: 1,
    })
    expect(stateFrom({ page: '0' }, all).page).toBe(1)
    expect(stateFrom({}, all)).toEqual({ domain: null, starred: false, page: 1 })
  })
})

describe('searchOf', () => {
  test('is empty for the defaults and round-trips otherwise', () => {
    expect(searchOf({ domain: null, starred: false, page: 1 })).toBe('')
    const state = { domain: fixtureWorkspace.id, starred: true, page: 2 }
    const query = searchOf(state)
    expect(query).toBe(`?domain=${fixtureWorkspace.id}&starred=1&page=2`)
    const params = Object.fromEntries(new URLSearchParams(query))
    expect(stateFrom(params, [fixtureWorkspace])).toEqual(state)
  })
})

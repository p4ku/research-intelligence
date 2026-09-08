import { fixtureEditions } from '@/lib/bff/briefings/fixtures'
import { fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { fixtureRuns } from '@/lib/bff/pipeline-runs/fixtures'
import type { T } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import {
  composeRows,
  currentRunId,
  filterRows,
  hasBriefing,
  paginate,
  PER_PAGE,
  searchOf,
  stateFrom,
  type ArchiveRow,
} from './rows'

const t: T = (s) => s
const edition = fixtureEditions[0]
// The archive joins on the run id; the fixtures share it.
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
    expect(row.brief.href).toBe(
      `/briefing/${edition.date}?domain=${edition.workspace_id}&run=${edition.run_id}`,
    )
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
    // Unless the corpus cap dropped older papers: then nothing is known, and the row stays.
    expect(
      composeRows({ editions: [unfilled], runs: [run], domains, t, lang: 'en', capped: true }),
    ).toHaveLength(1)
  })

  test('two runs of one domain on the same day are two rows, each linking to its own run', () => {
    const rerunId = '00000000-0000-4000-8000-000000000033'
    const rerun = {
      ...run,
      id: rerunId,
      started_at: '2026-08-31T12:00:00Z',
      completed_at: '2026-08-31T12:03:00Z',
    }
    const rerunEdition = { ...edition, run_id: rerunId, generated_at: rerun.completed_at }
    const rows = composeRows({
      editions: [rerunEdition, edition],
      runs: [rerun, run],
      domains,
      t,
      lang: 'en',
    })
    expect(rows.map((r) => r.id)).toEqual([rerunId, edition.run_id])
    expect(rows.map((r) => r.current)).toEqual([true, false])
    expect(new Set(rows.map((r) => r.brief.href)).size).toBe(2)
    expect(rows[1].brief.href).toContain(`&run=${edition.run_id}`)
    // Period and day read the same for both, so the clock tells them apart.
    expect(rows.map((r) => r.generated)).toEqual(['31 Aug 2026', '31 Aug 2026'])
    expect(rows[0].stamp).toBe('12:03 UTC')
    expect(rows[1].stamp).toMatch(/^\d\d:\d\d UTC$/)
  })

  test('a domain that briefed once in a day carries no clock', () => {
    const [row] = composeRows({ editions: [edition, older], runs: [run], domains, t, lang: 'en' })
    expect(row.stamp).toBeNull()
    // Two domains on one day are told apart by their names, not a clock.
    const other = {
      ...edition,
      run_id: '00000000-0000-4000-8000-000000000034',
      workspace_id: 'ws-2',
    }
    const rows = composeRows({
      editions: [edition, other],
      runs: [run],
      domains: { ...domains, 'ws-2': 'Other' },
      t,
      lang: 'en',
    })
    expect(rows.map((r) => r.stamp)).toEqual([null, null])
  })

  test('a completed run without a completion stamp still carries a clock, from its start', () => {
    const stampless = {
      ...run,
      id: '00000000-0000-4000-8000-000000000035',
      started_at: '2026-08-31T12:00:00Z',
      completed_at: null,
    }
    // Addressed by its trigger day, as the service composes it without a completion.
    const its = { ...edition, run_id: stampless.id, date: '2026-08-31', generated_at: null }
    const rows = composeRows({
      editions: [its, edition],
      runs: [stampless, run],
      domains,
      t,
      lang: 'en',
    })
    expect(rows.map((r) => r.generated)).toEqual(['31 Aug 2026', '31 Aug 2026'])
    expect(rows.map((r) => r.stamp)).toEqual(['12:00 UTC', '08:29 UTC'])
    // The cell prints the day the row's link opens, even when the start was another day.
    const nightOwl = { ...stampless, started_at: '2026-09-01T00:10:00Z' }
    const [row] = composeRows({ editions: [its], runs: [nightOwl], domains, t, lang: 'en' })
    expect(row.generated).toBe('31 Aug 2026')
    expect(row.brief.href).toContain('/briefing/2026-08-31?')
  })

  test('the pair is counted on the day the cell prints, so a midnight completion is the next day', () => {
    // The backend dated the edition 30 Aug; its run completed 00:20 on the 31st.
    const late = {
      ...run,
      id: older.run_id,
      started_at: '2026-08-30T23:40:00Z',
      completed_at: '2026-08-31T00:20:00Z',
    }
    const lateEdition = {
      ...edition,
      run_id: late.id,
      date: '2026-08-30',
      generated_at: late.completed_at,
    }
    const rows = composeRows({
      editions: [edition, lateEdition],
      runs: [run, late],
      domains,
      t,
      lang: 'en',
    })
    expect(rows.map((r) => r.generated)).toEqual(['31 Aug 2026', '31 Aug 2026'])
    expect(rows.map((r) => r.stamp)).toEqual(['08:29 UTC', '00:20 UTC'])
  })

  test('a same-day edition that is not a row does not make its twin carry a clock', () => {
    const emptyRun = {
      ...run,
      id: older.run_id,
      completed_at: '2026-08-31T15:30:00Z',
      total_papers_passed_screening: 0,
    }
    const emptyEdition = {
      ...edition,
      run_id: emptyRun.id,
      papers: [],
      generated_at: emptyRun.completed_at,
    }
    const rows = composeRows({
      editions: [emptyEdition, edition],
      runs: [emptyRun, run],
      domains,
      t,
      lang: 'en',
    })
    expect(rows.map((r) => r.id)).toEqual([edition.run_id])
    expect(rows[0].stamp).toBeNull()
  })

  test('the newest completion is current, even when an older run started later', () => {
    const slow = {
      ...run,
      id: older.run_id,
      started_at: '2026-08-31T06:00:00Z',
      completed_at: '2026-08-31T14:00:00Z',
    }
    const quick = {
      ...run,
      started_at: '2026-08-31T08:00:00Z',
      completed_at: '2026-08-31T08:03:00Z',
    }
    expect(currentRunId([quick, slow])).toBe(slow.id)
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

describe('hasBriefing', () => {
  test('needs papers that cleared screening and an edition that shows them', () => {
    expect(hasBriefing(25, edition, false)).toBe(true)
    expect(hasBriefing(0, edition, false)).toBe(false)
    expect(hasBriefing(25, null, false)).toBe(false)
    expect(hasBriefing(25, { papers: [] }, false)).toBe(false)
  })

  test('past the corpus cap an edition with no papers is unknowable, not empty', () => {
    expect(hasBriefing(25, { papers: [] }, true)).toBe(true)
    // The counter is the run's own, so a zero there is still a zero.
    expect(hasBriefing(0, { papers: [] }, true)).toBe(false)
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
    stamp: null,
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

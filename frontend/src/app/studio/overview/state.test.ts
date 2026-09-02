import { fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { fixtureOverviewRuns } from '@/lib/bff/pipeline-runs/fixtures'
import { fixtureBudgetWorkspace, fixtureEmptyWorkspace } from '@/lib/bff/workspaces/fixtures'
import { describe, expect, test } from 'bun:test'
import { indexRuns } from './derive'
import { announcementFor, reduce, toSearch, type OverviewState } from './state'

const NOW = '2026-09-01T09:15:00Z'
const ctx = { index: indexRuns(fixtureOverviewRuns), nowIso: NOW }
const RUNNING = '00000000-0000-4000-8000-000000000103'
const FAILED = '00000000-0000-4000-8000-000000000106'
const ABORTED = '00000000-0000-4000-8000-000000000105'
const base: OverviewState = { scope: 'all', runId: RUNNING, filter: 'all', level: 'list' }

describe('scope', () => {
  test('keeps the open run when it is still in scope, else opens the scope default (wide)', () => {
    const same = reduce(base, { type: 'scope', id: fixtureWorkspace.id, narrow: false }, ctx)
    expect(same.runId).toBe(RUNNING)
    const other = reduce(base, { type: 'scope', id: fixtureBudgetWorkspace.id, narrow: false }, ctx)
    expect(other.runId).toBe(FAILED)
    expect(other.level).toBe('list')
  })
  test('narrow: leaving the open run behind closes the pane instead of auto-opening', () => {
    const s = reduce(base, { type: 'scope', id: fixtureBudgetWorkspace.id, narrow: true }, ctx)
    expect(s.runId).toBeNull()
  })
  test('drops a status filter the new scope cannot satisfy', () => {
    const filtered = { ...base, filter: 'running' as const }
    expect(
      reduce(filtered, { type: 'scope', id: fixtureBudgetWorkspace.id, narrow: false }, ctx).filter,
    ).toBe('all')
    expect(
      reduce(filtered, { type: 'scope', id: fixtureWorkspace.id, narrow: false }, ctx).filter,
    ).toBe('running')
  })
  test('an empty workspace opens nothing', () => {
    const s = reduce(base, { type: 'scope', id: fixtureEmptyWorkspace.id, narrow: false }, ctx)
    expect(s.runId).toBeNull()
  })
})

describe('open and close', () => {
  test('wide: clicking the open row again closes; narrow never toggles', () => {
    expect(reduce(base, { type: 'open', id: RUNNING, narrow: false }, ctx).runId).toBeNull()
    expect(reduce(base, { type: 'open', id: RUNNING, narrow: true }, ctx)).toMatchObject({
      runId: RUNNING,
      level: 'detail',
    })
  })
  test('close returns to the list level only from the detail level', () => {
    expect(reduce({ ...base, level: 'detail' }, { type: 'close' }, ctx)).toMatchObject({
      runId: null,
      level: 'list',
    })
    expect(reduce({ ...base, level: 'rail' }, { type: 'close' }, ctx).level).toBe('rail')
  })
  test('widen opens the default run only when nothing is open', () => {
    expect(reduce({ ...base, runId: null }, { type: 'widen' }, ctx).runId).toBe(RUNNING)
    expect(reduce({ ...base, runId: FAILED }, { type: 'widen' }, ctx).runId).toBe(FAILED)
  })
})

describe('filter', () => {
  test('wide: a filter the open run does not match moves the pane to the first match', () => {
    const s = reduce(base, { type: 'filter', filter: 'aborted', narrow: false }, ctx)
    expect(s.runId).toBe(ABORTED)
    expect(s.filter).toBe('aborted')
  })
  test('narrow or a matching filter leaves the open run alone', () => {
    expect(reduce(base, { type: 'filter', filter: 'aborted', narrow: true }, ctx).runId).toBe(
      RUNNING,
    )
    expect(reduce(base, { type: 'filter', filter: 'running', narrow: false }, ctx).runId).toBe(
      RUNNING,
    )
  })
})

describe('url and announcements', () => {
  test('search string omits defaults', () => {
    expect(toSearch({ scope: 'all', runId: null, filter: 'all', level: 'list' })).toBe('')
    expect(toSearch({ scope: 'w1', runId: 'r1', filter: 'failed', level: 'detail' })).toBe(
      '?ws=w1&run=r1&status=failed',
    )
  })
  test('announces once per change of the open run', () => {
    const describe = (id: string) => `Run ${id.slice(0, 8)}`
    expect(announcementFor(base, base, describe)).toBeNull()
    expect(announcementFor(base, { ...base, runId: FAILED }, describe)).toBe('Run 00000000')
    expect(announcementFor(base, { ...base, runId: null }, describe)).toBe('Run detail closed.')
  })
})

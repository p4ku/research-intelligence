import { describe, expect, test } from 'bun:test'
import { byRunClock, runClock } from './clock'

const run = (id: string, over: { completed_at?: string | null; started_at?: string | null }) => ({
  id,
  run_date: '2026-08-31',
  started_at: null,
  completed_at: null,
  ...over,
})

describe('runClock', () => {
  test('completion, else start, else the trigger day', () => {
    expect(
      runClock(
        run('a', { started_at: '2026-08-31T08:00:00Z', completed_at: '2026-08-31T08:03:00Z' }),
      ),
    ).toBe('2026-08-31T08:03:00Z')
    expect(runClock(run('b', { started_at: '2026-08-31T09:00:00Z' }))).toBe('2026-08-31T09:00:00Z')
    expect(runClock(run('c', {}))).toBe('2026-08-31')
  })
})

describe('byRunClock', () => {
  test('a long run that started first and finished last is the newest', () => {
    const slow = run('slow', {
      started_at: '2026-08-31T06:00:00Z',
      completed_at: '2026-08-31T14:00:00Z',
    })
    const quick = run('quick', {
      started_at: '2026-08-31T08:00:00Z',
      completed_at: '2026-08-31T08:03:00Z',
    })
    expect([quick, slow].sort(byRunClock).map((r) => r.id)).toEqual(['slow', 'quick'])
    expect([slow, quick].sort(byRunClock).map((r) => r.id)).toEqual(['slow', 'quick'])
  })

  test('a run in flight ranks by its start among completions', () => {
    const done = run('done', {
      started_at: '2026-08-31T08:00:00Z',
      completed_at: '2026-08-31T09:30:00Z',
    })
    const flying = run('flying', { started_at: '2026-08-31T09:00:00Z' })
    const later = run('later', { started_at: '2026-08-31T10:00:00Z' })
    expect([flying, done, later].sort(byRunClock).map((r) => r.id)).toEqual([
      'later',
      'done',
      'flying',
    ])
  })
})

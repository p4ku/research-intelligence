import { describe, expect, test } from 'bun:test'
import {
  admission,
  inFlightFor,
  isInFlight,
  MAX_IN_FLIGHT_PER_DOMAIN,
  refusalDetail,
  sameWindow,
  type InFlightRun,
} from './admission'
import { fixtureRuns } from './fixtures'

const WS_A = '00000000-0000-4000-8000-0000000000a1'
const WS_B = '00000000-0000-4000-8000-0000000000b1'

function run(over: Partial<InFlightRun> = {}): InFlightRun {
  return {
    id: `00000000-0000-4000-8000-${String(Math.floor(Math.random() * 1e12)).padStart(12, '0')}`,
    workspace_id: WS_A,
    workspace_name: 'Hybrid Computing',
    status: 'running',
    period_start: null,
    period_end: null,
    lookback_days: 7,
    ...over,
  }
}

describe('isInFlight', () => {
  test('running and pending hold a slot; ended runs do not', () => {
    expect(isInFlight({ status: 'running' })).toBe(true)
    expect(isInFlight({ status: 'pending' })).toBe(true)
    expect(isInFlight({ status: 'completed' })).toBe(false)
    expect(isInFlight({ status: 'failed' })).toBe(false)
    expect(isInFlight({ status: 'aborted' })).toBe(false)
  })
})

describe('sameWindow', () => {
  test('explicit dates match on both days', () => {
    const r = run({ period_start: '2026-08-01', period_end: '2026-08-15', lookback_days: null })
    expect(
      sameWindow(r, { workspace_id: WS_A, start_date: '2026-08-01', end_date: '2026-08-15' }),
    ).toBe(true)
    expect(
      sameWindow(r, { workspace_id: WS_A, start_date: '2026-08-01', end_date: '2026-08-16' }),
    ).toBe(false)
  })

  test('a lookback matches only a lookback, and dates beat it', () => {
    expect(sameWindow(run({ lookback_days: 7 }), { workspace_id: WS_A, lookback_days: 7 })).toBe(
      true,
    )
    expect(sameWindow(run({ lookback_days: 7 }), { workspace_id: WS_A, lookback_days: 14 })).toBe(
      false,
    )
    expect(
      sameWindow(run({ lookback_days: 7 }), {
        workspace_id: WS_A,
        start_date: '2026-08-01',
        end_date: '2026-08-15',
      }),
    ).toBe(false)
  })

  test('an unknown window matches nothing, not even another unknown one', () => {
    const bare = run({ lookback_days: null })
    expect(sameWindow(bare, { workspace_id: WS_A })).toBe(false)
  })
})

describe('admission', () => {
  test('nothing in flight: admitted with a zero count', () => {
    expect(admission([], { workspace_id: WS_A, lookback_days: 7 })).toEqual({ ok: true, count: 0 })
  })

  test('the cap counts running and pending in the same domain only', () => {
    const runs = [
      ...Array.from({ length: MAX_IN_FLIGHT_PER_DOMAIN - 1 }, (_, i) =>
        run({ lookback_days: 10 + i, status: i % 2 ? 'pending' : 'running' }),
      ),
      run({ lookback_days: 99, status: 'completed' }),
      run({ workspace_id: WS_B, workspace_name: 'Other', lookback_days: 3 }),
    ]
    expect(admission(runs, { workspace_id: WS_A, lookback_days: 3 })).toEqual({
      ok: true,
      count: MAX_IN_FLIGHT_PER_DOMAIN - 1,
    })
    const full = [...runs, run({ lookback_days: 50 })]
    const verdict = admission(full, { workspace_id: WS_A, lookback_days: 3 })
    expect(verdict.ok).toBe(false)
    if (!verdict.ok) {
      expect(verdict.reason).toBe('cap')
      expect(verdict.domain).toBe('Hybrid Computing')
      expect(verdict.count).toBe(MAX_IN_FLIGHT_PER_DOMAIN)
      expect(refusalDetail(verdict)).toBe(
        '5 of 5 runs in progress for Hybrid Computing. Wait for one to finish.',
      )
    }
  })

  test('a twin window is refused below the cap, naming the run', () => {
    const twin = run({ period_start: '2026-08-01', period_end: '2026-08-15', lookback_days: null })
    const verdict = admission([twin], {
      workspace_id: WS_A,
      start_date: '2026-08-01',
      end_date: '2026-08-15',
    })
    expect(verdict).toEqual({
      ok: false,
      reason: 'duplicate',
      domain: 'Hybrid Computing',
      count: 1,
      run: twin,
    })
    if (!verdict.ok) {
      expect(refusalDetail(verdict)).toBe('Hybrid Computing is already running this search window.')
    }
  })

  test('the cap is checked before the window', () => {
    const runs = Array.from({ length: MAX_IN_FLIGHT_PER_DOMAIN }, () => run({ lookback_days: 7 }))
    const verdict = admission(runs, { workspace_id: WS_A, lookback_days: 7 })
    expect(verdict.ok).toBe(false)
    if (!verdict.ok) expect(verdict.reason).toBe('cap')
  })

  test('the fixtures: one run in flight on a 7-day lookback', () => {
    expect(inFlightFor(fixtureRuns, fixtureRuns[0].workspace_id).map((r) => r.id)).toEqual([
      fixtureRuns[2].id,
    ])
    const dup = admission(fixtureRuns, {
      workspace_id: fixtureRuns[0].workspace_id,
      lookback_days: 7,
    })
    expect(dup.ok).toBe(false)
    const fresh = admission(fixtureRuns, {
      workspace_id: fixtureRuns[0].workspace_id,
      start_date: '2026-08-01',
      end_date: '2026-08-31',
    })
    expect(fresh).toEqual({ ok: true, count: 1 })
  })
})

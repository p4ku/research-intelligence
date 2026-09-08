import { fixtureEditions } from '@/lib/bff/briefings/fixtures'
import type { Edition } from '@/lib/bff/briefings/schema'
import { fixtureRuns } from '@/lib/bff/pipeline-runs/fixtures'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { describe, expect, test } from 'bun:test'
import { inFlightIds, POLL_RUNS, RECENT, selectRecent } from './recent'

const [completed, failedRun, running] = fixtureRuns
const edition = fixtureEditions[0]

/** A run, newest first by `n` (started `n` days before the fixture). */
function run(n: number, patch: Partial<PipelineRun>): PipelineRun {
  const day = String(31 - n).padStart(2, '0')
  return {
    ...completed,
    id: `00000000-0000-4000-8000-0000000002${String(n).padStart(2, '0')}`,
    run_date: `2026-08-${day}`,
    started_at: `2026-08-${day}T08:00:00.000000Z`,
    completed_at: `2026-08-${day}T08:03:00.000000Z`,
    ...patch,
  }
}

/** Editions for the given runs, each with the fixture edition's papers. */
function editionsFor(runs: PipelineRun[], patch: Partial<Edition> = {}): Map<string, Edition> {
  return new Map(runs.map((r) => [r.id, { ...edition, run_id: r.id, date: r.run_date, ...patch }]))
}

describe('selectRecent', () => {
  test('a briefing is a row; a completed run that briefed nothing is not', () => {
    const briefed = run(1, {})
    const empty = run(0, { total_papers_passed_screening: 0 })
    const rows = selectRecent([empty, briefed], editionsFor([empty, briefed]), false)
    expect(rows.map((r) => r.run.id)).toEqual([briefed.id])
    expect(rows[0].edition?.run_id).toBe(briefed.id)
  })

  test('an edition that shows none of the papers the run passed is not a row, unless the corpus is capped', () => {
    const r = run(0, {})
    const bare = editionsFor([r], { papers: [] })
    expect(selectRecent([r], bare, false)).toEqual([])
    expect(selectRecent([r], bare, true)).toHaveLength(1)
    // No edition composed at all (its domain's corpus could not be read): never a row.
    expect(selectRecent([r], new Map(), true)).toEqual([])
  })

  test('two runs of one domain on the same day are two briefings, each with its own edition', () => {
    const first = run(0, { id: 'same-day-1' })
    const rerun = run(0, {
      id: 'same-day-2',
      started_at: '2026-08-31T12:00:00.000000Z',
      completed_at: '2026-08-31T12:03:00.000000Z',
    })
    const rows = selectRecent([rerun, first], editionsFor([rerun, first]), false)
    expect(rows.map((r) => r.run.id)).toEqual(['same-day-2', 'same-day-1'])
    expect(rows.map((r) => r.edition?.run_id)).toEqual(['same-day-2', 'same-day-1'])
  })

  test('only briefings count toward RECENT; runs in flight and failures ride along', () => {
    const briefings = Array.from({ length: RECENT + 2 }, (_, i) => run(i + 3, {}))
    const runs = [
      { ...running, id: 'r-flight', started_at: '2026-08-31T09:00:00.000000Z' },
      run(1, { id: 'r-failed', status: 'failed' }),
      run(2, { id: 'r-empty', total_papers_passed_screening: 0 }),
      ...briefings,
    ]
    const rows = selectRecent(runs, editionsFor(briefings), false)
    expect(rows.filter((r) => r.edition)).toHaveLength(RECENT)
    expect(rows.map((r) => r.run.id).slice(0, 2)).toEqual(['r-flight', 'r-failed'])
    expect(rows).toHaveLength(RECENT + 2)
    expect(rows.map((r) => r.run.id)).not.toContain(briefings[RECENT].id)
  })

  test('a run of failures cannot crowd the briefings out', () => {
    const briefing = run(9, {})
    const failures = Array.from({ length: 6 }, (_, i) => run(i, { status: 'failed' }))
    const rows = selectRecent([...failures, briefing], editionsFor([briefing]), false)
    expect(rows.map((r) => r.run.id)).toEqual([failures[0].id, briefing.id])
  })

  test('a failure shows only until its domain briefs again, and only the latest one', () => {
    const otherDomain = { workspace_id: '00000000-0000-4000-8000-0000000000aa' }
    const olderFailure = run(3, { id: 'f-old', status: 'failed' })
    const briefing = run(2, {})
    const newerFailureOtherDomain = run(1, { id: 'f-other', status: 'failed', ...otherDomain })
    const abortedOtherDomain = run(0, { id: 'a-other', status: 'aborted', ...otherDomain })
    const runs = [abortedOtherDomain, newerFailureOtherDomain, briefing, olderFailure]
    const rows = selectRecent(runs, editionsFor([briefing]), false)
    // The other domain's latest failure (aborted counts), then the briefing;
    // the fixture domain's older failure is superseded by its briefing.
    expect(rows.map((r) => r.run.id)).toEqual(['a-other', briefing.id])
  })

  test('the fixtures: the running run, the failed run and the briefing, in run order', () => {
    const runs = [running, completed, failedRun]
    const rows = selectRecent(runs, new Map([[edition.run_id, edition]]), false)
    expect(rows.map((r) => r.run.status)).toEqual(['running', 'completed'])
    expect(rows[1].edition).toBe(edition)
  })
})

describe('inFlightIds', () => {
  test('running and pending runs within the window, sorted', () => {
    const pending = { ...running, id: 'z-pending', status: 'pending' as const }
    expect(inFlightIds([running, completed, pending, failedRun])).toEqual([running.id, 'z-pending'])
  })

  test('ignores a run past the poll window, as the poll would', () => {
    const filler = Array.from({ length: POLL_RUNS }, (_, i) => ({ ...completed, id: `c${i}` }))
    expect(inFlightIds([...filler, running])).toEqual([])
    expect(inFlightIds([running, ...filler])).toEqual([running.id])
  })
})

import {
  FIXTURE_RERUN,
  FIXTURE_RUN,
  fixturePaperDTOs,
  fixturePapers,
  fixtureWorkspace,
} from '@/lib/bff/papers/fixtures'
import { fixtureRuns } from '@/lib/bff/pipeline-runs/fixtures'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { indexRuns } from '@/lib/papers/runs'
import { describe, expect, test } from 'bun:test'
import { briefs, composeEditions } from './compose'

// The morning run and its same-day rerun (the fixture runs), over the
// corpus as Django collapses it: paper 0 reports the rerun (its latest
// run), paper 1 the morning run.
const morning: PipelineRun = { ...fixtureRuns[0]!, id: FIXTURE_RUN }
const rerun: PipelineRun = {
  ...morning,
  id: FIXTURE_RERUN,
  started_at: '2026-08-31T12:00:00.000000Z',
  completed_at: '2026-08-31T12:03:00.000000Z',
  total_papers_fetched: 4,
  total_papers_passed_screening: 1,
}
const [paper0, paper1] = fixturePapers
const corpus = new Map([
  [paper0!.id, { ...paper0!, pipeline_run_id: FIXTURE_RERUN }],
  [paper1!.id, { ...paper1!, pipeline_run_id: FIXTURE_RUN }],
])
const index = indexRuns(fixturePaperDTOs)
const name = fixtureWorkspace.name

describe('composeEditions', () => {
  test('one edition per run that briefs, newest by completion first', () => {
    const editions = composeEditions([morning, rerun], name, corpus, index, 'en')
    expect(editions.map((e) => e.run_id)).toEqual([FIXTURE_RERUN, FIXTURE_RUN])
    expect(editions.map((e) => e.date)).toEqual(['2026-08-31', '2026-08-31'])
    expect(editions[0]!.generated_at).toBe(rerun.completed_at)
    // Whatever order the runs arrive in.
    expect(
      composeEditions([rerun, morning], name, corpus, index, 'en').map((e) => e.run_id),
    ).toEqual([FIXTURE_RERUN, FIXTURE_RUN])
  })

  test('a paper scored in both runs appears in each edition as that run recorded it', () => {
    const [asRerun, asMorning] = composeEditions([morning, rerun], name, corpus, index, 'en')
    // The morning run passed it at 87.5 — the rerun's 84 must not leak in.
    expect(asMorning!.papers.map((p) => [p.id, p.screening_status, p.signal_score])).toEqual([
      [paper0!.id, 'full_text_passed', 87.5],
    ])
    expect(asMorning!.exclusions.map((x) => x.paper_id)).toEqual([paper1!.id])
    expect(asMorning!.funnel).toEqual({ fetched: 10, passed_screening: 9, surfaced: 1 })
    // The rerun rescored it to 84 and saw nothing else.
    expect(asRerun!.papers.map((p) => [p.id, p.screening_status, p.signal_score])).toEqual([
      [paper0!.id, 'full_text_passed', 84],
    ])
    expect(asRerun!.exclusions).toEqual([])
    expect(asRerun!.funnel).toEqual({ fetched: 4, passed_screening: 1, surfaced: 1 })
  })

  test('a run that passed nothing, or did not complete, is not an edition', () => {
    const empty: PipelineRun = {
      ...rerun,
      id: '00000000-0000-4000-8000-000000000105',
      total_papers_fetched: 0,
      total_papers_passed_screening: 0,
    }
    const [, failed, running] = fixtureRuns
    const editions = composeEditions(
      [running!, empty, rerun, failed!, morning],
      name,
      corpus,
      index,
      'en',
    )
    expect(editions.map((e) => e.run_id)).toEqual([FIXTURE_RERUN, FIXTURE_RUN])
    expect(briefs(empty)).toBe(false)
    expect(briefs(failed!)).toBe(false)
    expect(briefs(running!)).toBe(false)
    expect(briefs(morning)).toBe(true)
  })

  test('without a run index the corpus’s own attribution stands: each paper belongs to the run it reports', () => {
    const [asRerun, asMorning] = composeEditions([morning, rerun], name, corpus, null, 'en')
    // Paper 0 reports the rerun, with the corpus's current (collapsed) score.
    expect(asRerun!.papers.map((p) => [p.id, p.signal_score])).toEqual([[paper0!.id, 87.5]])
    expect(asRerun!.exclusions).toEqual([])
    // The morning run keeps only paper 1 — its own record of paper 0 is out of reach.
    expect(asMorning!.papers).toEqual([])
    expect(asMorning!.exclusions.map((x) => x.paper_id)).toEqual([paper1!.id])
  })
})

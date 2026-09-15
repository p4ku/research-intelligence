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
import type { ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { briefs, composeEditions } from './compose'
import { fixtureEditions } from './fixtures'
import type { Edition } from './schema'

// The fixture runs — the morning run and its same-day rerun — over the
// corpus as Django collapses it: paper 0 reports the rerun (its latest
// run), paper 1 the morning run.
const morning = fixtureRuns.find((r) => r.id === FIXTURE_RUN)!
const rerun = fixtureRuns.find((r) => r.id === FIXTURE_RERUN)!
const [paper0, paper1] = fixturePapers
const corpus = new Map<string, ScoredPaper>([
  [paper0!.id, { ...paper0!, pipeline_run_id: FIXTURE_RERUN }],
  [paper1!.id, { ...paper1!, pipeline_run_id: FIXTURE_RUN }],
])
const index = indexRuns(fixturePaperDTOs)
const name = fixtureWorkspace.name

/** An edition without its prose, which the fixtures write by hand. */
function shape({ run_id, workspace_id, date, funnel, papers, exclusions, generated_at }: Edition) {
  return { run_id, workspace_id, date, funnel, papers, exclusions, generated_at }
}

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
    expect(asMorning!.funnel).toEqual({
      fetched: morning.total_papers_fetched,
      passed_screening: morning.total_papers_passed_screening,
      surfaced: 1,
    })
    // The rerun rescored it to 84 and saw nothing else.
    expect(asRerun!.papers.map((p) => [p.id, p.screening_status, p.signal_score])).toEqual([
      [paper0!.id, 'full_text_passed', 84],
    ])
    expect(asRerun!.exclusions).toEqual([])
    expect(asRerun!.funnel).toEqual({
      fetched: rerun.total_papers_fetched,
      passed_screening: rerun.total_papers_passed_screening,
      surfaced: 1,
    })
  })

  test('the edition fixtures are what the composition makes of the run and paper fixtures', () => {
    // So the stub source, the gallery and the spec examples cannot drift
    // from the run and paper fixtures with the suite green. The failed and
    // running fixture runs compose nothing.
    const composed = composeEditions(fixtureRuns, name, corpus, index, 'en')
    expect(composed.map(shape)).toEqual(fixtureEditions.map(shape))
  })

  test('surfaced papers are signal-first; withdrawn papers are exclusions with their reason', () => {
    const row = fixturePaperDTOs[0]!.metrics[0]!
    const more = [
      { id: '00000000-0000-4000-8000-000000000043', score: 91.25, status: 'full_text_passed' },
      { id: '00000000-0000-4000-8000-000000000044', score: 12, status: 'full_text_passed' },
      { id: '00000000-0000-4000-8000-000000000045', score: null, status: 'withdrawn' },
    ]
    const dtos = more.map((m, i) => ({
      ...fixturePaperDTOs[0]!,
      id: m.id,
      title: `Paper ${m.id.slice(-2)}`,
      metrics: [
        {
          ...row,
          id: `00000000-0000-4000-8000-0000000006${String(i).padStart(2, '0')}`,
          paper: m.id,
          signal_score: m.score,
          screening_status: m.status,
          full_text_screening_reasoning:
            m.status === 'withdrawn' ? 'Withdrawn by the authors after the rerun.' : null,
        },
      ],
    }))
    const wide = new Map(corpus)
    for (const m of more) wide.set(m.id, { ...paper0!, id: m.id, title: `Paper ${m.id.slice(-2)}` })
    const [asRerun] = composeEditions(
      [rerun],
      name,
      wide,
      indexRuns([...fixturePaperDTOs, ...dtos]),
      'en',
    )
    expect(asRerun!.papers.map((p) => p.signal_score)).toEqual([91.25, 84, 12])
    expect(asRerun!.funnel.surfaced).toBe(3)
    expect(asRerun!.exclusions).toEqual([
      {
        paper_id: more[2]!.id,
        title: 'Paper 45',
        source: paper0!.source,
        reason: 'Withdrawn by the authors after the rerun.',
        published_date: paper0!.published_date,
        source_url: paper0!.source_url,
      },
    ])
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
    // Paper 0 reports the rerun, with whatever score the corpus carries.
    expect(asRerun!.papers.map((p) => [p.id, p.signal_score])).toEqual([[paper0!.id, 87.5]])
    expect(asRerun!.exclusions).toEqual([])
    // The morning run keeps only paper 1 — its own record of paper 0 is out of reach.
    expect(asMorning!.papers).toEqual([])
    expect(asMorning!.exclusions.map((x) => x.paper_id)).toEqual([paper1!.id])
  })
})

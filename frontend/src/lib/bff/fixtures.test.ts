// Drift guard: every checked-in fixture must parse against its contract
// schema — the same schemas the OpenAPI spec and conformance checker use.
import { describe, expect, test } from 'bun:test'
import { fixtureEditions } from './briefings/fixtures'
import { edition } from './briefings/schema'
import { fixtureSessionDetails, fixtureSessions, fixtureStreamFrames } from './chat/fixtures'
import { chatEvent, chatSession, chatSessionDetail } from './chat/schema'
import { fixtureSteps, fixtureStepsFailed } from './component-runs/fixtures'
import { componentRun } from './component-runs/schema'
import { fixturePapers, fixtureWorkspace } from './papers/fixtures'
import { scoredPaper } from './papers/schema'
import { fixtureOverviewRuns, fixtureRunDetail, fixtureRuns } from './pipeline-runs/fixtures'
import { pipelineRun, pipelineRunDetail } from './pipeline-runs/schema'
import { fixtureWorkspaces } from './workspaces/fixtures'
import { workspace } from './workspaces/schema'

describe('fixtures match their contract schemas', () => {
  test('papers', () => {
    for (const fixture of fixturePapers) {
      const parsed = scoredPaper.safeParse(fixture)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
  })
  test('workspace', () => {
    const parsed = workspace.safeParse(fixtureWorkspace)
    expect(parsed.success ? null : parsed.error.issues).toBeNull()
  })
  test('chat sessions and stream frames', () => {
    for (const f of fixtureSessions) {
      const parsed = chatSession.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
    for (const f of fixtureSessionDetails) {
      const parsed = chatSessionDetail.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
    for (const f of fixtureStreamFrames) {
      const parsed = chatEvent.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
    // The stream must terminate: without a final done frame, every stubbed
    // answer would settle as a cut (consume-stream.ts treats no-done as failure).
    expect(fixtureStreamFrames.at(-1)?.event).toBe('done')
  })
  test('briefing editions', () => {
    for (const f of fixtureEditions) {
      const parsed = edition.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
  })
  test('workspaces for the overview', () => {
    for (const f of fixtureWorkspaces) {
      const parsed = workspace.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
    // Every overview run belongs to a fixture workspace, so the rail and the
    // list agree on what exists.
    const ids = new Set(fixtureWorkspaces.map((w) => w.id))
    for (const run of fixtureOverviewRuns) expect(ids.has(run.workspace_id)).toBe(true)
  })
  test('pipeline runs and their steps', () => {
    for (const f of [...fixtureRuns, ...fixtureOverviewRuns]) {
      const parsed = pipelineRun.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
    const detail = pipelineRunDetail.safeParse(fixtureRunDetail)
    expect(detail.success ? null : detail.error.issues).toBeNull()
    for (const f of [...fixtureSteps, ...fixtureStepsFailed]) {
      const parsed = componentRun.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
    // The failed steps belong to a run the overview fixtures list as failed.
    const failedRun = fixtureOverviewRuns.find(
      (r) => r.id === fixtureStepsFailed[0].pipeline_run_id,
    )
    expect(failedRun?.status).toBe('failed')
  })
})

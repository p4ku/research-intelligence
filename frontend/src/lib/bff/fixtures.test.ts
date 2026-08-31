// Drift guard: every checked-in fixture must parse against its contract
// schema — the same schemas the OpenAPI spec and conformance checker use.
import { describe, expect, test } from 'bun:test'
import { fixtureEditions } from './briefings/fixtures'
import { edition } from './briefings/schema'
import { fixtureSessionDetails, fixtureSessions, fixtureStreamFrames } from './chat/fixtures'
import { chatEvent, chatSession, chatSessionDetail } from './chat/schema'
import { fixturePapers, fixtureWorkspace } from './papers/fixtures'
import { scoredPaper } from './papers/schema'
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
  })
  test('briefing editions', () => {
    for (const f of fixtureEditions) {
      const parsed = edition.safeParse(f)
      expect(parsed.success ? null : parsed.error.issues).toBeNull()
    }
  })
})

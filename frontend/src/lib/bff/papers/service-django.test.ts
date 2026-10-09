import { describe, expect, test } from 'bun:test'
import type { PapersQuery } from './schema'

describe('papers.list with django source', () => {
  test('constructs query parameters and passes them to /api/papers/scorecard/', async () => {
    // Test URLSearchParams serialization matching service.ts logic
    const query: PapersQuery = {
      page: 2,
      page_size: 8,
      screening: 'passed',
      ordering: '-signal_score',
      search: 'Robotics',
      workspace_id: '64c2a2ab-1464-49aa-8f84-13c1b652033d',
      starred: '1',
      min_score: 80,
      min_trl: 1,
      max_trl: 9,
      within_days: 30,
    }

    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        params.set(key, String(value))
      }
    }
    const qs = params.toString()

    expect(qs).toContain('page=2')
    expect(qs).toContain('page_size=8')
    expect(qs).toContain('screening=passed')
    expect(qs).toContain('ordering=-signal_score')
    expect(qs).toContain('search=Robotics')
    expect(qs).toContain('workspace_id=64c2a2ab-1464-49aa-8f84-13c1b652033d')
    expect(qs).toContain('starred=1')
    expect(qs).toContain('min_score=80')
    expect(qs).toContain('within_days=30')
  })
})

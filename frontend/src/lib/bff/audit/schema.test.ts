import { describe, expect, mock, test } from 'bun:test'

mock.module('server-only', () => ({}))

import { mockCohortDetail1, mockPaperDetail1, mockQueueItems } from './fixtures'
import { auditCohortDetail, auditPaperDetail, auditQueueItem, submitAuditDecision } from './schema'

describe('SLR Audit BFF Schemas', () => {
  test('auditQueueItem parses mock queue items cleanly', () => {
    for (const item of mockQueueItems) {
      const parsed = auditQueueItem.parse(item)
      expect(parsed.cohort_id).toBe(item.cohort_id)
      expect(parsed.remaining_count).toBe(item.remaining_count)
      expect(parsed.gate).toBe('full_text_screening')
    }
  })

  test('auditPaperDetail parses full paper review context', () => {
    const parsed = auditPaperDetail.parse(mockPaperDetail1)
    expect(parsed.paper_id).toBe(mockPaperDetail1.paper_id)
    expect(parsed.ai_decision).toBe('include')
    expect(parsed.evidence_quotes.length).toBeGreaterThan(0)
    expect(parsed.current_index).toBe(5)
    expect(parsed.total_count).toBe(10)
  })

  test('submitAuditDecision validates agree and override decisions', () => {
    const agree = submitAuditDecision.parse({
      action: 'agree',
    })
    expect(agree.action).toBe('agree')

    const override = submitAuditDecision.parse({
      action: 'override_exclude',
      exclusion_reason: 'In-Vitro / Lab Only',
      reviewer_note: 'No animal or human in vivo data reported in study.',
      evidence_citation: 'Page 3, paragraph 2',
    })
    expect(override.action).toBe('override_exclude')
    expect(override.exclusion_reason).toBe('In-Vitro / Lab Only')
  })

  test('auditCohortDetail parses cohort summary and paper item list', () => {
    const parsed = auditCohortDetail.parse(mockCohortDetail1)
    expect(parsed.cohort_id).toBe(mockCohortDetail1.cohort_id)
    expect(parsed.total_papers).toBe(10)
    expect(parsed.papers.length).toBe(3)
  })
})

describe('SLR Audit BFF Service (Stub mode)', () => {
  test('getMyQueue returns mock queue items when stub is active', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { audit } = await import('./service')
    const queue = await audit.getMyQueue()
    expect(queue.length).toBeGreaterThanOrEqual(1)
    expect(queue[0].gate).toBe('full_text_screening')
  })

  test('getCohort returns mock cohort details in stub mode', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { audit } = await import('./service')
    const cohort = await audit.getCohort(mockCohortDetail1.cohort_id)
    expect(cohort.stage).toBe('full_text_screening')
    expect(cohort.total_papers).toBe(10)
  })

  test('getPaper returns mock paper details in stub mode', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { audit } = await import('./service')
    const paper = await audit.getPaper(mockCohortDetail1.cohort_id, mockPaperDetail1.paper_id)
    expect(paper.title).toContain('Lassa fever')
    expect(paper.ai_decision).toBe('include')
  })

  test('submitReview returns review confirmation in stub mode', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { audit } = await import('./service')
    const res = await audit.submitReview(mockCohortDetail1.cohort_id, mockPaperDetail1.paper_id, {
      action: 'agree',
    })
    expect(res.status).toBe('reviewed')
    expect(res.decision).toBe('include')
  })
})

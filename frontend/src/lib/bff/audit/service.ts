/**
 * SLR Audit BFF service.
 * Connects to Django /api/slr/ endpoints with fallback to fixtures in stub mode.
 * Server-only.
 */
import 'server-only'

import * as z from 'zod'
import { django } from '../core/http'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { mockCohortDetail1, mockPaperDetail1, mockQueueItems, mockReviewResult } from './fixtures'
import {
  auditCohortDetail,
  auditPaperDetail,
  auditQueueItem,
  auditReviewResult,
  type AuditCohortDetail,
  type AuditPaperDetail,
  type AuditQueueItem,
  type AuditReviewResult,
  type SubmitAuditDecision,
  type SubmitExtractionAuditDecision,
} from './schema'

export const audit = {
  /**
   * Retrieves active audit cohorts for the logged in reviewer.
   */
  async getMyQueue(): Promise<AuditQueueItem[]> {
    if (sourceOf('audit') === 'stub') {
      return mockQueueItems
    }
    return django('/api/slr/cohorts/my-queue/', z.array(auditQueueItem))
  },

  /**
   * Retrieves cohort metadata and list of papers.
   */
  async getCohort(cohortId: string): Promise<AuditCohortDetail> {
    const cid = assertUuid(cohortId, 'cohort_id')
    if (sourceOf('audit') === 'stub') {
      return mockCohortDetail1
    }
    return django(`/api/slr/cohorts/${cid}/`, auditCohortDetail)
  },

  /**
   * Retrieves full details, AI reasoning, and PDF URL for an individual paper in a cohort.
   */
  async getPaper(cohortId: string, paperId: string): Promise<AuditPaperDetail> {
    const cid = assertUuid(cohortId, 'cohort_id')
    const pid = assertUuid(paperId, 'paper_id')
    if (sourceOf('audit') === 'stub') {
      return { ...mockPaperDetail1, cohort_id: cid, paper_id: pid }
    }
    return django(`/api/slr/cohorts/${cid}/papers/${pid}/`, auditPaperDetail)
  },

  /**
   * Submits a reviewer vote (Agree or Override) for a paper.
   */
  async submitReview(
    cohortId: string,
    paperId: string,
    input: SubmitAuditDecision,
  ): Promise<AuditReviewResult> {
    const cid = assertUuid(cohortId, 'cohort_id')
    const pid = assertUuid(paperId, 'paper_id')
    if (sourceOf('audit') === 'stub') {
      return mockReviewResult
    }
    return django(`/api/slr/cohorts/${cid}/papers/${pid}/review/`, auditReviewResult, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(input),
    })
  },

  /**
   * Submits an auditor verification/modification/rejection for a single parameter extraction.
   */
  async submitExtractionReview(
    cohortId: string,
    extractionId: string,
    input: SubmitExtractionAuditDecision,
  ): Promise<{
    status: string
    review_id: string
    action: string
    is_cohort_complete: boolean
    next_unreviewed_paper_id?: string | null
    pipeline_resumed?: boolean
  }> {
    const cid = assertUuid(cohortId, 'cohort_id')
    const eid = assertUuid(extractionId, 'extraction_id')
    if (sourceOf('audit') === 'stub') {
      return {
        status: 'saved',
        review_id: eid,
        action: input.action,
        is_cohort_complete: false,
        next_unreviewed_paper_id: null,
        pipeline_resumed: false,
      }
    }
    const resSchema = z.object({
      status: z.string(),
      review_id: z.uuid(),
      action: z.string(),
      is_cohort_complete: z.boolean(),
      next_unreviewed_paper_id: z.uuid().nullable().optional(),
      pipeline_resumed: z.boolean().optional(),
    })
    return django(`/api/slr/cohorts/${cid}/extractions/${eid}/audit/`, resSchema, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(input),
    })
  },

  /**
   * Resumes a paused SLR pipeline run.
   */
  async resumeRun(runId: string): Promise<{ status: string; pipeline_run_id: string }> {
    const rid = assertUuid(runId, 'run_id')
    const schema = z.object({
      status: z.string().optional(),
      resumed: z.boolean().optional(),
      pipeline_run_id: z.uuid(),
    })
    if (sourceOf('audit') === 'stub') {
      return { status: 'resumed', pipeline_run_id: rid }
    }
    const res = await django(`/api/slr/runs/${rid}/resume/`, schema, {
      method: 'POST',
    })
    return {
      status: res.status || (res.resumed ? 'resumed' : 'unknown'),
      pipeline_run_id: res.pipeline_run_id,
    }
  },
}

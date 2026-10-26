/**
 * SLR Stage 2 BFF Service: Quality metrics, PRISMA flow, RoB 2, and Arbiter console.
 * Server-only module that queries Django REST API or returns fixtures in stub mode.
 */
import 'server-only'

import * as z from 'zod'
import { django } from '../core/http'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import {
  mockDisputes,
  mockPrismaMetrics,
  mockRobAssessments,
  mockSLRRuns,
} from './fixtures'
import {
  resolveDisputeInputSchema,
  slrDisputeSchema,
  slrPipelineRunItemSchema,
  slrPrismaMetricsSchema,
  slrRobAssessmentSchema,
  type ResolveDisputeInput,
  type SLRDispute,
  type SLRPipelineRunItem,
  type SLRPRISMAMetrics,
  type SLRROBAssessment,
} from './schema'

export const slr = {
  /**
   * Retrieves SLR pipeline execution runs for the run switcher.
   */
  async getRuns(): Promise<SLRPipelineRunItem[]> {
    if (sourceOf('audit') === 'stub') {
      return mockSLRRuns
    }
    try {
      // Query pipeline runs from backend
      const rawRuns = await django('/api/pipeline-runs/', z.array(z.any()))
      return rawRuns.map((r: any) => ({
        id: String(r.id),
        name: r.name || r.workspace?.name || `Run ${String(r.id).slice(0, 8)}`,
        workspace_id: String(r.workspace?.id || r.workspace_id || ''),
        workspace_name: r.workspace?.name || 'SLR Workspace',
        status: String(r.status || 'unknown'),
        created_at: String(r.created_at || new Date().toISOString()),
      }))
    } catch {
      return mockSLRRuns
    }
  },

  /**
   * Retrieves PRISMA 2020 flow metrics & Cohen's Kappa / AI calibration statistics.
   */
  async getMetrics(runId: string): Promise<SLRPRISMAMetrics> {
    const rid = assertUuid(runId, 'run_id')
    if (sourceOf('audit') === 'stub') {
      return { ...mockPrismaMetrics, pipeline_run: rid }
    }
    return django(`/api/slr/runs/${rid}/prisma/`, slrPrismaMetricsSchema)
  },

  /**
   * Retrieves Cochrane Risk of Bias assessments for included studies.
   */
  async getRiskOfBias(runId: string): Promise<SLRROBAssessment[]> {
    const rid = assertUuid(runId, 'run_id')
    if (sourceOf('audit') === 'stub') {
      return mockRobAssessments.map((r) => ({ ...r, pipeline_run: rid }))
    }
    return django(`/api/slr/runs/${rid}/rob/`, z.array(slrRobAssessmentSchema))
  },

  /**
   * Retrieves list of reviewer disputes requiring arbitration.
   */
  async getDisputes(statusFilter: string = 'all'): Promise<SLRDispute[]> {
    if (sourceOf('audit') === 'stub') {
      if (statusFilter === 'all') return mockDisputes
      return mockDisputes.filter((d) => d.status === statusFilter)
    }
    const query = statusFilter === 'all' ? '' : `?status=${encodeURIComponent(statusFilter)}`
    return django(`/api/slr/disputes/${query}`, z.array(slrDisputeSchema))
  },

  /**
   * Issues a binding Senior Arbiter ruling for a contested paper.
   */
  async resolveDispute(
    disputeId: string,
    input: ResolveDisputeInput,
  ): Promise<{ success: boolean; dispute_id: string; status: string; final_decision: string }> {
    const did = assertUuid(disputeId, 'dispute_id')
    resolveDisputeInputSchema.parse(input)

    if (sourceOf('audit') === 'stub') {
      const found = mockDisputes.find((d) => d.id === did)
      if (found) {
        found.status = 'resolved'
        found.final_decision = input.final_decision
        found.resolution_rationale = input.resolution_rationale
        found.final_exclusion_reason = input.final_exclusion_reason || null
        found.resolved_at = new Date().toISOString()
      }
      return {
        success: true,
        dispute_id: did,
        status: 'resolved',
        final_decision: input.final_decision,
      }
    }

    const resSchema = z.object({
      success: z.boolean(),
      dispute_id: z.string(),
      status: z.string(),
      final_decision: z.string(),
    })

    return django(`/api/slr/disputes/${did}/resolve/`, resSchema, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(input),
    })
  },
}

import { describe, expect, test } from 'bun:test'
import {
  resolveDisputeInputSchema,
  slrDisputeSchema,
  slrPipelineRunItemSchema,
  slrPrismaMetricsSchema,
  slrRobAssessmentSchema,
} from '@/lib/bff/slr/schema'
import {
  mockDisputes,
  mockPrismaMetrics,
  mockRobAssessments,
  mockSLRRuns,
} from '@/lib/bff/slr/fixtures'

describe('SLR Stage 2 BFF Schema & Contract Validation', () => {
  test('validates PRISMA 2020 metrics schema against mock payload', () => {
    const parsed = slrPrismaMetricsSchema.parse(mockPrismaMetrics)
    expect(parsed.records_identified_total).toBe(480)
    expect(parsed.studies_included_synthesis).toBe(32)
    expect(parsed.human_inter_rater_kappa).toBe(0.88)
    expect(parsed.ai_vs_human_kappa).toBe(0.84)
  })

  test('validates Risk of Bias assessment schema against mock payload', () => {
    for (const rob of mockRobAssessments) {
      const parsed = slrRobAssessmentSchema.parse(rob)
      expect(parsed.paper_title).toBeTruthy()
      expect(parsed.overall_bias).toMatch(/low_risk|some_concerns|high_risk/)
      expect(parsed.traffic_light_color).toMatch(/green|yellow|red/)
    }
  })

  test('validates Adjudication Dispute schema against mock payload', () => {
    for (const dispute of mockDisputes) {
      const parsed = slrDisputeSchema.parse(dispute)
      expect(parsed.paper_title).toBeTruthy()
      expect(parsed.evidence_synthesis).toBeDefined()
    }
  })

  test('validates Resolve Dispute Input schema correctly', () => {
    const validInclude = resolveDisputeInputSchema.parse({
      final_decision: 'include',
      resolution_rationale: 'Binding ruling: empirical model matches inclusion criteria.',
    })
    expect(validInclude.final_decision).toBe('include')

    const validExclude = resolveDisputeInputSchema.parse({
      final_decision: 'exclude',
      resolution_rationale: 'Binding ruling: solely animal model without human transmission.',
      final_exclusion_reason: 'Solely Animal Study (No Transmission Parameters)',
    })
    expect(validExclude.final_decision).toBe('exclude')
    expect(validExclude.final_exclusion_reason).toBe('Solely Animal Study (No Transmission Parameters)')

    expect(() => {
      resolveDisputeInputSchema.parse({
        final_decision: 'invalid_decision',
        resolution_rationale: 'x',
      })
    }).toThrow()
  })

  test('validates SLR Pipeline Run Item schema', () => {
    for (const run of mockSLRRuns) {
      const parsed = slrPipelineRunItemSchema.parse(run)
      expect(parsed.id).toBeTruthy()
      expect(parsed.workspace_name).toBeTruthy()
    }
  })
})

import * as z from 'zod'

/**
 * PRISMA 2020 Statement flow metrics and inter-rater agreement statistics.
 */
export const slrPrismaMetricsSchema = z.object({
  id: z.string(),
  pipeline_run: z.string(),
  records_identified_total: z.number().int().nonnegative().default(0),
  records_by_source: z.record(z.string(), z.number()).default({}),
  duplicates_removed: z.number().int().nonnegative().default(0),
  records_screened_abstract: z.number().int().nonnegative().default(0),
  records_excluded_abstract: z.number().int().nonnegative().default(0),
  abstract_exclusion_reasons: z.record(z.string(), z.number()).default({}),
  full_text_assessed: z.number().int().nonnegative().default(0),
  full_text_excluded: z.number().int().nonnegative().default(0),
  full_text_exclusion_reasons: z.record(z.string(), z.number()).default({}),
  studies_included_synthesis: z.number().int().nonnegative().default(0),
  studies_included_meta_analysis: z.number().int().nonnegative().default(0),
  human_inter_rater_kappa: z.number().nullable().optional(),
  ai_vs_human_kappa: z.number().nullable().optional(),
  ai_sensitivity: z.number().nullable().optional(),
  ai_specificity: z.number().nullable().optional(),
  generated_at: z.string().optional(),
})

export type SLRPRISMAMetrics = z.infer<typeof slrPrismaMetricsSchema>

/**
 * Domain evaluation item inside Risk of Bias.
 */
export const robDomainScoreSchema = z.object({
  rating: z.enum(['low_risk', 'some_concerns', 'high_risk', 'critical_risk', 'unclear']).or(z.string()),
  quote: z.string().nullable().optional(),
  page: z.number().nullable().optional(),
})

export type ROBDomainScore = z.infer<typeof robDomainScoreSchema>

/**
 * Risk of Bias assessment for an included study (RoB 2, ROBINS-I, NOS).
 */
export const slrRobAssessmentSchema = z.object({
  id: z.string(),
  paper: z.string(),
  paper_title: z.string(),
  pipeline_run: z.string(),
  framework: z.enum(['rob2', 'robins_i', 'nos']).or(z.string()).default('rob2'),
  domain_scores: z.record(z.string(), robDomainScoreSchema.or(z.any())).default({}),
  overall_bias: z.enum(['low_risk', 'some_concerns', 'high_risk', 'critical_risk']).or(z.string()).default('some_concerns'),
  traffic_light_color: z.enum(['green', 'yellow', 'red']).or(z.string()).default('yellow'),
  is_human_verified: z.boolean().default(false),
  human_notes: z.string().nullable().optional(),
})

export type SLRROBAssessment = z.infer<typeof slrRobAssessmentSchema>

/**
 * Reviewer Adjudication Dispute record.
 */
export const slrDisputeSchema = z.object({
  id: z.string(),
  sample_cohort: z.string(),
  paper: z.string(),
  paper_title: z.string(),
  paper_doi: z.string().nullable().optional(),
  stage: z.enum(['abstract', 'full_text']).or(z.string()),
  status: z.enum(['pending', 'resolved']).or(z.string()),
  arbiter: z.number().nullable().optional(),
  final_decision: z.enum(['include', 'exclude']).nullable().optional(),
  final_exclusion_reason: z.string().nullable().optional(),
  resolution_rationale: z.string().nullable().optional(),
  evidence_synthesis: z.record(z.string(), z.any()).default({}),
  created_at: z.string(),
  resolved_at: z.string().nullable().optional(),
})

export type SLRDispute = z.infer<typeof slrDisputeSchema>

/**
 * Payload to resolve a dispute by Senior Arbiter.
 */
export const resolveDisputeInputSchema = z.object({
  final_decision: z.enum(['include', 'exclude']),
  resolution_rationale: z.string().min(3, 'Rationale is required'),
  final_exclusion_reason: z.string().nullable().optional(),
})

export type ResolveDisputeInput = z.infer<typeof resolveDisputeInputSchema>

/**
 * SLR Pipeline Run summary item for the console switcher.
 */
export const slrPipelineRunItemSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  workspace_id: z.string(),
  workspace_name: z.string(),
  status: z.string(),
  created_at: z.string(),
})

export type SLRPipelineRunItem = z.infer<typeof slrPipelineRunItemSchema>

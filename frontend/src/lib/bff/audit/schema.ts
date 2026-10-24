import * as z from 'zod'

export const auditGate = z.enum([
  'abstract_screening',
  'full_text_screening',
  'parameter_extraction',
])
export type AuditGate = z.infer<typeof auditGate>

export const auditStatus = z.enum(['pending', 'in_review', 'completed'])
export type AuditStatus = z.infer<typeof auditStatus>

export const auditQueueItem = z
  .object({
    cohort_id: z.uuid(),
    pipeline_run_id: z.uuid(),
    workspace_id: z.uuid(),
    workspace_name: z.string(),
    briefing_name: z.string(),
    gate: auditGate,
    assigned_count: z.number().int(),
    completed_count: z.number().int(),
    remaining_count: z.number().int(),
    status: auditStatus,
    created_at: z.iso.datetime({ offset: true }),
  })
  .meta({ id: 'AuditQueueItem' })
export type AuditQueueItem = z.infer<typeof auditQueueItem>

export const evidenceQuote = z.object({
  quote: z.string(),
  page_number: z.number().nullable().optional(),
  section: z.string().nullable().optional(),
})
export type EvidenceQuote = z.infer<typeof evidenceQuote>

export const auditExtractionItem = z.object({
  extraction_id: z.uuid(),
  category: z.string(),
  parameter_name: z.string(),
  extracted_value: z.string(),
  uncertainty: z.string().nullable().optional(),
  method: z.string().nullable().optional(),
  text_evidence: z.string().nullable().optional(),
  page_number: z.number().nullable().optional(),
  status: z.enum(['pending', 'verify', 'modify', 'reject', 'verified', 'modified', 'rejected']).default('pending'),
})
export type AuditExtractionItem = z.infer<typeof auditExtractionItem>

export const auditPaperDetail = z
  .object({
    paper_id: z.uuid(),
    cohort_id: z.uuid(),
    title: z.string(),
    authors: z.string(),
    journal: z.string().nullable(),
    publication_year: z.number().nullable(),
    doi: z.string().nullable(),
    pdf_url: z.string().nullable(),
    has_full_text: z.boolean(),
    abstract: z.string().nullable(),

    // AI Decision & Evidence
    ai_decision: z.enum(['include', 'exclude']),
    ai_confidence: z.number().min(0).max(1),
    ai_reasoning: z.string(),
    matched_criteria: z.array(z.string()),
    evidence_quotes: z.array(evidenceQuote),

    // Human Review State
    is_reviewed: z.boolean(),
    reviewer_decision: z.string().nullable(),
    exclusion_reason: z.string().nullable(),
    reviewer_note: z.string().nullable(),
    evidence_citation: z.string().nullable(),
    reviewed_at: z.iso.datetime({ offset: true }).nullable(),

    // Navigation
    current_index: z.number().int(),
    total_count: z.number().int(),
    prev_paper_id: z.uuid().nullable(),
    next_paper_id: z.uuid().nullable(),

    // Parameter Extractions (Gate 2 / Extraction Audit)
    extractions: z.array(auditExtractionItem).optional().default([]),
  })
  .meta({ id: 'AuditPaperDetail' })
export type AuditPaperDetail = z.infer<typeof auditPaperDetail>

export const submitAuditDecision = z
  .object({
    action: z.enum(['agree', 'override_include', 'override_exclude']),
    exclusion_reason: z.string().optional().nullable(),
    reviewer_note: z.string().optional().nullable(),
    evidence_citation: z.string().optional().nullable(),
    time_spent_seconds: z.number().int().optional(),
  })
  .meta({ id: 'SubmitAuditDecision' })
export type SubmitAuditDecision = z.infer<typeof submitAuditDecision>

export const submitExtractionAuditDecision = z
  .object({
    action: z.enum(['verify', 'modify', 'reject']),
    corrected_fields: z.record(z.string(), z.any()).optional().nullable(),
    verified_evidence_quotes: z.array(z.record(z.string(), z.any())).optional(),
    reviewer_notes: z.string().optional().nullable(),
    time_spent_seconds: z.number().int().optional(),
  })
  .meta({ id: 'SubmitExtractionAuditDecision' })
export type SubmitExtractionAuditDecision = z.infer<typeof submitExtractionAuditDecision>

export const auditReviewResult = z
  .object({
    status: z.string(),
    review_id: z.uuid(),
    decision: z.string(),
    is_cohort_complete: z.boolean(),
    next_unreviewed_paper_id: z.uuid().nullable(),
    pipeline_resumed: z.boolean(),
  })
  .meta({ id: 'AuditReviewResult' })
export type AuditReviewResult = z.infer<typeof auditReviewResult>

export const auditCohortPaperItem = z.object({
  paper_id: z.uuid(),
  index: z.number().int(),
  title: z.string(),
  doi: z.string().nullable(),
  is_reviewed: z.boolean(),
})
export type AuditCohortPaperItem = z.infer<typeof auditCohortPaperItem>

export const auditCohortDetail = z
  .object({
    cohort_id: z.uuid(),
    pipeline_run_id: z.uuid(),
    stage: auditGate,
    is_audit_complete: z.boolean(),
    total_papers: z.number().int(),
    completed_count: z.number().int(),
    first_unreviewed_paper_id: z.uuid().nullable(),
    papers: z.array(auditCohortPaperItem),
  })
  .meta({ id: 'AuditCohortDetail' })
export type AuditCohortDetail = z.infer<typeof auditCohortDetail>

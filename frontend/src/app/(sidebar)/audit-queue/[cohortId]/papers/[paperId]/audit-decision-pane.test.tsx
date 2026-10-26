import type { AuditPaperDetail } from '@/lib/bff/audit/schema'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { AuditDecisionPane } from './audit-decision-pane'

const unreviewedPaper: AuditPaperDetail = {
  paper_id: 'd0a80123-0000-4000-8000-000000000001',
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  title: 'Immune Checkpoint Inhibitor RCT in NSCLC',
  authors: 'Carter et al.',
  journal: 'NEJM',
  publication_year: 2024,
  doi: '10.1056/NEJMoa240001',
  pdf_url: '/api/papers/d0a80123-0000-4000-8000-000000000001/pdf/',
  has_full_text: true,
  abstract: 'Phase III clinical trial assessing overall survival with pembrolizumab...',
  ai_decision: 'include',
  ai_confidence: 0.96,
  ai_reasoning: 'Clear randomized controlled trial meeting all inclusion criteria for NSCLC.',
  matched_criteria: ['RCT design', 'NSCLC cohort', 'Overall Survival primary endpoint'],
  evidence_quotes: [
    {
      quote: 'Median overall survival was 22.0 months vs 10.6 months.',
      page_number: 4,
      section: 'Results',
    },
  ],
  is_reviewed: false,
  reviewer_decision: null,
  exclusion_reason: null,
  reviewer_note: null,
  evidence_citation: null,
  reviewed_at: null,
  current_index: 1,
  total_count: 4,
  prev_paper_id: null,
  next_paper_id: 'd0a80123-0000-4000-8000-000000000002',
  extractions: [],
}

const alreadyReviewedPaper: AuditPaperDetail = {
  ...unreviewedPaper,
  is_reviewed: true,
  reviewer_decision: 'override_exclude',
  exclusion_reason: 'In-Vitro / Lab Only',
  reviewer_note: 'Corrected assessment upon full-text analysis.',
  reviewed_at: '2026-10-21T10:00:00Z',
}

describe('AuditDecisionPane Component Rendering', () => {
  test('renders AI decision context, confidence, reasoning and criteria', () => {
    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={unreviewedPaper}
        onSubmitted={() => {}}
      />,
    )

    expect(html).toContain('AI DECISION: include')
    expect(html).toContain('Confidence: 96%')
    expect(html).toContain('AI Chain-of-Thought Rationale')
    expect(html).toContain(
      'Clear randomized controlled trial meeting all inclusion criteria for NSCLC.',
    )

    // Eligibility criteria
    expect(html).toContain('RCT design')
    expect(html).toContain('NSCLC cohort')
    expect(html).toContain('Overall Survival primary endpoint')
  })

  test('renders audit verdict options and submit button for unreviewed paper', () => {
    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={unreviewedPaper}
        onSubmitted={() => {}}
      />,
    )

    expect(html).toContain('YOUR AUDIT VERDICT')
    expect(html).toContain('Agree with AI Decision (INCLUDE)')
    expect(html).toContain('Override → Disagree &amp; Exclude')
    expect(html).toContain('Submit &amp; Next Article (Cmd+Enter)')
  })

  test('renders update verdict button for already reviewed paper', () => {
    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={alreadyReviewedPaper}
        onSubmitted={() => {}}
      />,
    )

    expect(html).toContain('Update Verdict &amp; Next (Cmd+Enter)')
  })

  test('renders parameter extraction audit panel when isExtractionStage is true and paper has extractions', () => {
    const paperWithExtractions: AuditPaperDetail = {
      ...unreviewedPaper,
      extractions: [
        {
          extraction_id: 'a0a80123-0000-4000-8000-000000000001',
          category: 'epidemiology',
          parameter_name: 'Basic Reproduction Number (R0)',
          extracted_value: '1.34',
          uncertainty: '95% CI (1.12 - 1.61)',
          method: 'Maximum Likelihood',
          text_evidence: 'Estimated R0 of 1.34',
          page_number: 3,
          status: 'pending',
        },
      ],
    }

    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={paperWithExtractions}
        onSubmitted={() => {}}
        isExtractionStage={true}
      />,
    )

    expect(html).toContain('AI EXTRACTION AUDIT PANEL')
    expect(html).toContain('PARAMETER 1: Basic Reproduction Number (R0)')
    expect(html).toContain('1.34')
    expect(html).toContain('Maximum Likelihood')
    expect(html).toContain('✓ Verify')
    expect(html).toContain('✎ Modify')
    expect(html).toContain('✕ Reject')
    expect(html).toContain('Submit Extraction Audit &amp; Next (Cmd+Enter)')
    expect(html).toContain('Grounding Citation (Page 3)')
    expect(html).toContain('Jump to Page in PDF ↗')
  })

  test('renders AI grounding evidence quote cards and active focus state', () => {
    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={unreviewedPaper}
        onSubmitted={() => {}}
        activeEvidence={{
          quote: 'Median overall survival was 22.0 months vs 10.6 months.',
          page_number: 4,
          section: 'Results',
        }}
      />,
    )

    expect(html).toContain('AI Grounding Evidence (1)')
    expect(html).toContain('Median overall survival was 22.0 months vs 10.6 months.')
    expect(html).toContain('Page 4')
    expect(html).toContain('Section: Results')
    expect(html).toContain('🎯 Focused in Viewer')
  })

  test('renders Verify All button and keyboard shortcut legend in extraction stage', () => {
    const paperWithExtractions: AuditPaperDetail = {
      ...unreviewedPaper,
      extractions: [
        {
          extraction_id: 'a0a80123-0000-4000-8000-000000000001',
          category: 'epidemiology',
          parameter_name: 'Mortality Rate',
          extracted_value: '29%',
          uncertainty: null,
          method: null,
          text_evidence: 'Mortality reduced to 29%',
          page_number: 1,
          status: 'pending',
        },
      ],
    }

    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={paperWithExtractions}
        onSubmitted={() => {}}
        isExtractionStage={true}
      />,
    )

    // Verify All button rendered with count
    expect(html).toContain('All Verified')
    expect(html).toContain('title="Mark all parameters as verified"')

    // Keyboard shortcut legend
    expect(html).toContain('⌘↵')
    expect(html).toContain('Submit')
    expect(html).toContain('Navigate')
  })

  test('renders screening keyboard shortcuts (A for Agree, O for Override, arrows for Navigate)', () => {
    const html = renderToStaticMarkup(
      <AuditDecisionPane
        cohortId="c0a80123-0000-4000-8000-000000000001"
        paper={unreviewedPaper}
        onSubmitted={() => {}}
        isExtractionStage={false}
      />,
    )

    expect(html).toContain('⌘↵')
    expect(html).toContain('>A<')
    expect(html).toContain('Agree')
    expect(html).toContain('>O<')
    expect(html).toContain('Override')
    expect(html).toContain('Navigate')
  })
})

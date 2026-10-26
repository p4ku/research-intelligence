import type { AuditPaperDetail } from '@/lib/bff/audit/schema'
import { auditPaperDetail } from '@/lib/bff/audit/schema'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { AuditDecisionPane } from './audit-decision-pane'
import { PdfViewerPane } from './pdf-viewer-pane'

// Fixture 1: Paper with rich grounding evidence and parameter citations
const paperWithEvidence: AuditPaperDetail = {
  paper_id: 'd0a80123-0000-4000-8000-000000000001',
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  title: 'Phase III Trial of Monoclonal Antibody mAb114 in Ebola',
  authors: 'Mulangu et al.',
  journal: 'NEJM',
  publication_year: 2024,
  doi: '10.1056/NEJMoa1910993',
  pdf_url: '/api/papers/d0a80123-0000-4000-8000-000000000001/pdf/',
  has_full_text: true,
  abstract:
    'Randomized controlled trial of 681 patients. Overall mortality in the mAb114 group was 35.1% compared with 49.7% with ZMapp. Viral clearance was achieved rapidly in patients presenting with low initial viral load.',
  ai_decision: 'include',
  ai_confidence: 0.98,
  ai_reasoning:
    'High-rigour phase III human randomized controlled trial with verified survival outcome.',
  matched_criteria: ['Human RCT', 'Ebola Virus', 'Mortality primary endpoint'],
  evidence_quotes: [
    {
      quote: 'Overall mortality in the mAb114 group was 35.1% compared with 49.7%',
      page_number: 3,
      section: 'Results',
    },
    {
      quote:
        'Viral clearance was achieved rapidly in patients presenting with low initial viral load',
      page_number: 6,
      section: 'Discussion',
    },
  ],
  is_reviewed: false,
  reviewer_decision: null,
  exclusion_reason: null,
  reviewer_note: null,
  evidence_citation: null,
  reviewed_at: null,
  current_index: 1,
  total_count: 3,
  prev_paper_id: null,
  next_paper_id: 'd0a80123-0000-4000-8000-000000000002',
  extractions: [
    {
      extraction_id: 'a0a80123-0000-4000-8000-000000000001',
      category: 'Clinical Efficacy',
      parameter_name: 'Mortality Rate (mAb114 arm)',
      extracted_value: '35.1%',
      uncertainty: '95% CI (29.2% - 41.3%)',
      method: 'Kaplan-Meier survival estimator',
      text_evidence: 'Overall mortality in the mAb114 group was 35.1%',
      page_number: 3,
      status: 'pending',
    },
    {
      extraction_id: 'a0a80123-0000-4000-8000-000000000002',
      category: 'Virology',
      parameter_name: 'Viral Clearance Time',
      extracted_value: '48 hours',
      uncertainty: null,
      method: 'RT-PCR threshold cycle assay',
      text_evidence: 'Viral clearance was achieved rapidly within 48 hours',
      page_number: 6,
      status: 'pending',
    },
  ],
}

// Fixture 2: Paper with NO evidence quotes and NO extraction citations (Empty / Null state)
const paperWithoutEvidence: AuditPaperDetail = {
  paper_id: 'd0a80123-0000-4000-8000-000000000002',
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  title: 'General Review of Filovirus Therapeutics',
  authors: 'Generic Reviewer Group',
  journal: null,
  publication_year: 2023,
  doi: null,
  pdf_url: null,
  has_full_text: false,
  abstract:
    'Narrative summary of historical therapeutic strategies without quantitative parameters.',
  ai_decision: 'exclude',
  ai_confidence: 0.85,
  ai_reasoning: 'Narrative review article without primary experimental or clinical data.',
  matched_criteria: [],
  evidence_quotes: [], // Empty list!
  is_reviewed: false,
  reviewer_decision: null,
  exclusion_reason: null,
  reviewer_note: null,
  evidence_citation: null,
  reviewed_at: null,
  current_index: 2,
  total_count: 3,
  prev_paper_id: 'd0a80123-0000-4000-8000-000000000001',
  next_paper_id: null,
  extractions: [
    {
      extraction_id: 'a0a80123-0000-4000-8000-000000000003',
      category: 'General',
      parameter_name: 'Qualitative Assessment',
      extracted_value: 'Descriptive Only',
      uncertainty: null,
      method: null,
      text_evidence: null, // No text evidence!
      page_number: null, // No page number!
      status: 'pending',
    },
  ],
}

describe('Evidence & Grounding Linking Integration Tests', () => {
  describe('A. Paper WITH rich evidence quotes', () => {
    test('PdfViewerPane sets anchor parameters with page and search query in PDF mode', () => {
      const activeEvidence = {
        quote: 'Overall mortality in the mAb114 group was 35.1%',
        page_number: 3,
        section: 'Results',
      }

      const html = renderToStaticMarkup(
        <PdfViewerPane paper={paperWithEvidence} activeEvidence={activeEvidence} />,
      )

      // Active Evidence Focus Bar
      expect(html).toContain('Evidence Citation (Page 3, Results)')
      expect(html).toContain('Overall mortality in the mAb114 group was 35.1%')
      expect(html).toContain('PDF Page 3 ↗')
      expect(html).toContain('Highlight in Text 🔍')

      // PDF iframe anchor has #page=3&search=...
      expect(html).toContain('#page=3&amp;search=Overall%20mortality%20in%20the%20mAb114')

      // Floating jump card
      expect(html).toContain('🎯 Focused on Page 3')
      expect(html).toContain('Open in Tab ↗')
    })

    test('PdfViewerPane highlights matching quote with <mark> element in Text mode', () => {
      const activeEvidence = {
        quote: 'Overall mortality in the mAb114 group was 35.1%',
        page_number: 3,
      }

      // Render with pdf_url=null to force Text/OCR mode
      const html = renderToStaticMarkup(
        <PdfViewerPane
          paper={{ ...paperWithEvidence, pdf_url: null }}
          activeEvidence={activeEvidence}
        />,
      )

      expect(html).toContain('Highlighted matches shown below')
      expect(html).toContain('<mark')
      expect(html).toContain('Overall mortality in the mAb114 group was 35.1%')
    })

    test('AuditDecisionPane renders interactive AI Grounding Evidence quote cards in Section A', () => {
      const activeEvidence = {
        quote: 'Overall mortality in the mAb114 group was 35.1% compared with 49.7%',
        page_number: 3,
        section: 'Results',
      }

      const html = renderToStaticMarkup(
        <AuditDecisionPane
          cohortId="c0a80123-0000-4000-8000-000000000001"
          paper={paperWithEvidence}
          onSubmitted={() => {}}
          activeEvidence={activeEvidence}
        />,
      )

      expect(html).toContain('AI Grounding Evidence (2)')
      expect(html).toContain('Overall mortality in the mAb114 group was 35.1% compared with 49.7%')
      expect(html).toContain('Page 3')
      expect(html).toContain('Section: Results')
      expect(html).toContain('🎯 Focused in Viewer')

      // Second evidence quote also present
      expect(html).toContain(
        'Viral clearance was achieved rapidly in patients presenting with low initial viral load',
      )
      expect(html).toContain('Page 6')
      expect(html).toContain('Locate in PDF ↗')
    })

    test('AuditDecisionPane renders interactive parameter extraction grounding citations in Section B', () => {
      const activeEvidence = {
        quote: 'Overall mortality in the mAb114 group was 35.1%',
        page_number: 3,
      }

      const html = renderToStaticMarkup(
        <AuditDecisionPane
          cohortId="c0a80123-0000-4000-8000-000000000001"
          paper={paperWithEvidence}
          onSubmitted={() => {}}
          isExtractionStage={true}
          activeEvidence={activeEvidence}
        />,
      )

      expect(html).toContain('AI EXTRACTION AUDIT PANEL')
      expect(html).toContain('PARAMETER 1: Mortality Rate (mAb114 arm)')
      expect(html).toContain('Grounding Citation (Page 3)')
      expect(html).toContain('🎯 Active in PDF')

      expect(html).toContain('PARAMETER 2: Viral Clearance Time')
      expect(html).toContain('Grounding Citation (Page 6)')
      expect(html).toContain('Jump to Page in PDF ↗')
    })
  })

  describe('B. Paper WITHOUT evidence quotes (Graceful Fallback / Empty State)', () => {
    test('PdfViewerPane renders clean fallback without focus bar when activeEvidence is null', () => {
      const html = renderToStaticMarkup(
        <PdfViewerPane paper={paperWithoutEvidence} activeEvidence={null} />,
      )

      // No evidence banner should be present
      expect(html).not.toContain('Evidence Citation')
      expect(html).not.toContain('Focused Evidence')
      expect(html).not.toContain('🎯 Focused on Page')

      // Plain abstract text rendered without <mark>
      expect(html).toContain(
        'Narrative summary of historical therapeutic strategies without quantitative parameters.',
      )
      expect(html).not.toContain('<mark')
      expect(html).not.toContain('Highlighted matches shown below')

      // Extracted Evidence Quotes section is omitted when empty
      expect(html).not.toContain('Extracted Evidence Quotes')
    })

    test('PdfViewerPane renders default PDF toolbar with no #page fragment when activeEvidence is null', () => {
      const paperWithPdfOnly = {
        ...paperWithoutEvidence,
        pdf_url: '/api/papers/d0a80123-0000-4000-8000-000000000002/pdf/',
      }

      const html = renderToStaticMarkup(
        <PdfViewerPane paper={paperWithPdfOnly} activeEvidence={null} />,
      )

      expect(html).toContain(
        'src="/bff/papers/d0a80123-0000-4000-8000-000000000002/pdf#toolbar=1&amp;navpanes=0"',
      )
      expect(html).not.toContain('#page=')
      expect(html).not.toContain('&amp;search=')
    })

    test('AuditDecisionPane safely omits AI Grounding Evidence section when list is empty', () => {
      const html = renderToStaticMarkup(
        <AuditDecisionPane
          cohortId="c0a80123-0000-4000-8000-000000000001"
          paper={paperWithoutEvidence}
          onSubmitted={() => {}}
          activeEvidence={null}
        />,
      )

      expect(html).toContain('AI DECISION: exclude')
      expect(html).not.toContain('AI Grounding Evidence')
      expect(html).not.toContain('Locate in PDF ↗')
    })

    test('AuditDecisionPane handles extractions with null text_evidence without errors', () => {
      const html = renderToStaticMarkup(
        <AuditDecisionPane
          cohortId="c0a80123-0000-4000-8000-000000000001"
          paper={paperWithoutEvidence}
          onSubmitted={() => {}}
          isExtractionStage={true}
          activeEvidence={null}
        />,
      )

      expect(html).toContain('AI EXTRACTION AUDIT PANEL')
      expect(html).toContain('PARAMETER 1: Qualitative Assessment')
      expect(html).toContain('Descriptive Only')
      // No grounding citation button rendered since text_evidence is null
      expect(html).not.toContain('Grounding Citation')
      expect(html).not.toContain('Jump to Page in PDF ↗')
    })
  })

  describe('C. Frontend-Backend Schema Contract Validation', () => {
    test('auditPaperDetail Zod schema validates rich paper payload from Django API', () => {
      const validated = auditPaperDetail.parse(paperWithEvidence)
      expect(validated.paper_id).toBe('d0a80123-0000-4000-8000-000000000001')
      expect(validated.evidence_quotes.length).toBe(2)
      expect(validated.evidence_quotes[0].page_number).toBe(3)
      expect(validated.evidence_quotes[0].section).toBe('Results')
      expect(validated.extractions?.length).toBe(2)
      expect(validated.extractions?.[0].extracted_value).toBe('35.1%')
      expect(validated.extractions?.[0].page_number).toBe(3)
    })

    test('auditPaperDetail Zod schema validates empty evidence paper payload from Django API', () => {
      const validated = auditPaperDetail.parse(paperWithoutEvidence)
      expect(validated.paper_id).toBe('d0a80123-0000-4000-8000-000000000002')
      expect(validated.evidence_quotes).toEqual([])
      expect(validated.extractions?.length).toBe(1)
      expect(validated.extractions?.[0].text_evidence).toBeNull()
      expect(validated.extractions?.[0].page_number).toBeNull()
    })
  })
})

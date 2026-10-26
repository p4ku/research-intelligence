import type { AuditPaperDetail } from '@/lib/bff/audit/schema'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PdfViewerPane } from './pdf-viewer-pane'

const paperWithPdf: AuditPaperDetail = {
  paper_id: 'd0a80123-0000-4000-8000-000000000001',
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  title: 'Clinical Evaluation of Antiviral Therapies in Lassa Fever',
  authors: 'S. K. Baize, et al.',
  journal: 'Lancet Infectious Diseases',
  publication_year: 2022,
  doi: '10.1016/S1473-3099(22)00001-X',
  pdf_url: '/api/papers/d0a80123-0000-4000-8000-000000000001/pdf/',
  has_full_text: true,
  abstract: 'Randomized clinical trial assessing oral ribavirin vs standard of care...',
  ai_decision: 'include',
  ai_confidence: 0.95,
  ai_reasoning: 'Primary clinical efficacy trial with clear end-points.',
  matched_criteria: ['Human clinical trial', 'Lassa pathogen'],
  evidence_quotes: [],
  is_reviewed: false,
  reviewer_decision: null,
  exclusion_reason: null,
  reviewer_note: null,
  evidence_citation: null,
  reviewed_at: null,
  current_index: 1,
  total_count: 5,
  prev_paper_id: null,
  next_paper_id: 'd0a80123-0000-4000-8000-000000000002',
  extractions: [],
}

const paperWithoutPdf: AuditPaperDetail = {
  ...paperWithPdf,
  pdf_url: null,
  has_full_text: false,
}

describe('PdfViewerPane Component Rendering', () => {
  test('renders PDF viewer iframe and download button when pdf_url is available', () => {
    const html = renderToStaticMarkup(<PdfViewerPane paper={paperWithPdf} />)

    expect(html).toContain('PDF Mode')
    expect(html).toContain('Markdown / Text Mode')
    expect(html).toContain('Download PDF ↗')
    expect(html).toContain(
      'src="/bff/papers/d0a80123-0000-4000-8000-000000000001/pdf#toolbar=1&amp;navpanes=0"',
    )
    expect(html).toContain(
      'title="PDF viewer for Clinical Evaluation of Antiviral Therapies in Lassa Fever"',
    )
  })

  test('renders active evidence focus banner and adjusts PDF iframe anchor hash with page and search query', () => {
    const html = renderToStaticMarkup(
      <PdfViewerPane
        paper={paperWithPdf}
        activeEvidence={{
          quote: 'oral ribavirin vs standard of care',
          page_number: 3,
          section: 'Methods',
        }}
      />,
    )

    // Focus bar with page citation
    expect(html).toContain('Evidence Citation (Page 3, Methods)')
    expect(html).toContain('oral ribavirin vs standard of care')
    expect(html).toContain('PDF Page 3 ↗')
    expect(html).toContain('Highlight in Text 🔍')

    // Iframe URL anchor contains #page=3&search=...
    expect(html).toContain('#page=3&amp;search=oral%20ribavirin%20vs%20standard%20of')

    // Floating badge
    expect(html).toContain('Focused on Page 3')
  })

  test('renders markdown abstract view and warning banner when pdf_url is missing', () => {
    const html = renderToStaticMarkup(<PdfViewerPane paper={paperWithoutPdf} />)

    // Warning banner
    expect(html).toContain('PDF binary not available in storage')
    expect(html).toContain('Reading from Abstract &amp; Extracted Metadata')

    // Paper metadata and abstract
    expect(html).toContain('Clinical Evaluation of Antiviral Therapies in Lassa Fever')
    expect(html).toContain('S. K. Baize, et al.')
    expect(html).toContain('Lancet Infectious Diseases')
    expect(html).toContain('2022')
    expect(html).toContain('href="https://doi.org/10.1016/S1473-3099(22)00001-X"')
    expect(html).toContain(
      'Randomized clinical trial assessing oral ribavirin vs standard of care...',
    )
  })

  test('highlights matching evidence in text mode with mark element', () => {
    const html = renderToStaticMarkup(
      <PdfViewerPane
        paper={paperWithoutPdf}
        activeEvidence={{
          quote: 'Randomized clinical trial assessing oral ribavirin',
          page_number: 1,
        }}
      />,
    )

    // Check mark tag rendered around matched text
    expect(html).toContain('<mark')
    expect(html).toContain('Randomized clinical trial assessing oral ribavirin')
    expect(html).toContain('Highlighted matches shown below')
  })
})

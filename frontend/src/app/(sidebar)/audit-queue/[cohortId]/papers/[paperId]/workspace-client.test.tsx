import type { AuditCohortDetail, AuditPaperDetail } from '@/lib/bff/audit/schema'
import { describe, expect, mock, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

const mockPush = mock(() => {})
const mockPrefetch = mock(() => {})
const mockRefresh = mock(() => {})

mock.module('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    prefetch: mockPrefetch,
    refresh: mockRefresh,
  }),
  usePathname: () => '/audit-queue',
  useSearchParams: () => new URLSearchParams(),
}))

const { WorkspaceClient } = await import('./workspace-client')

const sampleCohort: AuditCohortDetail = {
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  pipeline_run_id: 'f0a80123-0000-4000-8000-000000000001',
  stage: 'abstract_screening',
  is_audit_complete: false,
  total_papers: 5,
  completed_count: 2,
  first_unreviewed_paper_id: 'd0a80123-0000-4000-8000-000000000002',
  papers: [],
}

const samplePaper: AuditPaperDetail = {
  paper_id: 'd0a80123-0000-4000-8000-000000000001',
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  title: 'Ribavirin Clinical Trial in Arenaviruses',
  authors: 'McCormick et al.',
  journal: 'Lancet',
  publication_year: 2023,
  doi: '10.1016/S0140-6736',
  pdf_url: '/api/papers/d0a80123-0000-4000-8000-000000000001/pdf/',
  has_full_text: true,
  abstract: 'Controlled clinical investigation of antiviral efficacy...',
  ai_decision: 'include',
  ai_confidence: 0.94,
  ai_reasoning: 'Direct clinical trial on targeted pathogen.',
  matched_criteria: ['RCT design', 'Pathogen match'],
  evidence_quotes: [
    {
      quote: 'Early ribavirin treatment reduced case fatality to 9%.',
      page_number: 2,
      section: 'Results',
    },
  ],
  is_reviewed: false,
  reviewer_decision: null,
  exclusion_reason: null,
  reviewer_note: null,
  evidence_citation: null,
  reviewed_at: null,
  current_index: 2,
  total_count: 5,
  prev_paper_id: 'd0a80123-0000-4000-8000-000000000000',
  next_paper_id: 'd0a80123-0000-4000-8000-000000000002',
}

describe('WorkspaceClient Component Rendering and Preloading', () => {
  test('renders workspace layout with ReviewHeader, PdfViewerPane and AuditDecisionPane', () => {
    const html = renderToStaticMarkup(
      <WorkspaceClient
        cohortId={sampleCohort.cohort_id}
        paper={samplePaper}
        cohort={sampleCohort}
      />,
    )

    expect(html).toContain('HITL Systematic Review Audit')
    expect(html).toContain('Ribavirin Clinical Trial in Arenaviruses')
    expect(html).toContain('AI DECISION: include')
    expect(html).toContain('Confidence: 94%')
  })

  test('injects link rel="prefetch" for next paper PDF binary when next_paper_id exists', () => {
    const html = renderToStaticMarkup(
      <WorkspaceClient
        cohortId={sampleCohort.cohort_id}
        paper={samplePaper}
        cohort={sampleCohort}
      />,
    )

    expect(html).toContain(
      '<link rel="prefetch" href="/bff/papers/d0a80123-0000-4000-8000-000000000002/pdf" as="fetch" crossorigin="anonymous"/>',
    )
  })

  test('omits link rel="prefetch" when next_paper_id is null', () => {
    const lastPaper: AuditPaperDetail = {
      ...samplePaper,
      next_paper_id: null,
    }

    const html = renderToStaticMarkup(
      <WorkspaceClient
        cohortId={sampleCohort.cohort_id}
        paper={lastPaper}
        cohort={sampleCohort}
      />,
    )

    expect(html).not.toContain('rel="prefetch"')
  })
})

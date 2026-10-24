import type { AuditCohortDetail } from '@/lib/bff/audit/schema'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReviewHeader } from './review-header'

const sampleCohort: AuditCohortDetail = {
  cohort_id: 'c0a80123-0000-4000-8000-000000000001',
  pipeline_run_id: 'f0a80123-0000-4000-8000-000000000001',
  stage: 'abstract_screening',
  is_audit_complete: false,
  total_papers: 3,
  completed_count: 1,
  first_unreviewed_paper_id: 'd0a80123-0000-4000-8000-000000000002',
  papers: [
    {
      paper_id: 'd0a80123-0000-4000-8000-000000000001',
      index: 1,
      title: 'Study 1 on Lassa Virus',
      doi: '10.1038/s41467-021-0001',
      is_reviewed: true,
    },
    {
      paper_id: 'd0a80123-0000-4000-8000-000000000002',
      index: 2,
      title: 'Study 2 on Ebola Virus',
      doi: '10.1038/s41467-021-0002',
      is_reviewed: false,
    },
    {
      paper_id: 'd0a80123-0000-4000-8000-000000000003',
      index: 3,
      title: 'Study 3 on Marburg Virus',
      doi: null,
      is_reviewed: false,
    },
  ],
}

describe('ReviewHeader Component Rendering', () => {
  test('renders back button and breadcrumbs', () => {
    const html = renderToStaticMarkup(
      <ReviewHeader
        cohortId={sampleCohort.cohort_id}
        currentIndex={2}
        totalCount={3}
        prevPaperId="d0a80123-0000-4000-8000-000000000001"
        nextPaperId="d0a80123-0000-4000-8000-000000000003"
        cohort={sampleCohort}
      />,
    )

    expect(html).toContain('href="/audit-queue"')
    expect(html).toContain('← Queue')
    expect(html).toContain('HITL Systematic Review Audit')
  })

  test('displays correct gate badge for abstract screening', () => {
    const html = renderToStaticMarkup(
      <ReviewHeader
        cohortId={sampleCohort.cohort_id}
        currentIndex={2}
        totalCount={3}
        prevPaperId={null}
        nextPaperId={null}
        cohort={{ ...sampleCohort, stage: 'abstract_screening' }}
      />,
    )
    expect(html).toContain('Gate 1: Abstract')
  })

  test('displays correct gate badge for full text screening', () => {
    const html = renderToStaticMarkup(
      <ReviewHeader
        cohortId={sampleCohort.cohort_id}
        currentIndex={2}
        totalCount={3}
        prevPaperId={null}
        nextPaperId={null}
        cohort={{ ...sampleCohort, stage: 'full_text_screening' }}
      />,
    )
    expect(html).toContain('Gate 2: Full-Text')
  })

  test('displays correct gate badge for parameter extraction', () => {
    const html = renderToStaticMarkup(
      <ReviewHeader
        cohortId={sampleCohort.cohort_id}
        currentIndex={2}
        totalCount={3}
        prevPaperId={null}
        nextPaperId={null}
        cohort={{ ...sampleCohort, stage: 'parameter_extraction' }}
      />,
    )
    expect(html).toContain('Gate 3: Extraction')
  })

  test('renders progress text and dot links with proper navigation state', () => {
    const html = renderToStaticMarkup(
      <ReviewHeader
        cohortId={sampleCohort.cohort_id}
        currentIndex={1}
        totalCount={3}
        prevPaperId={null}
        nextPaperId="d0a80123-0000-4000-8000-000000000002"
        cohort={sampleCohort}
      />,
    )

    expect(html).toContain('Progress: <strong class="text-zinc-900 dark:text-white">1</strong> of 3')
    expect(html).toContain('title="Paper 1: Study 1 on Lassa Virus"')
    expect(html).toContain('title="Paper 2: Study 2 on Ebola Virus"')

    // Prev is disabled (prevPaperId is null)
    expect(html).toContain('← Prev')
    // Next is active
    expect(html).toContain('href="/audit-queue/c0a80123-0000-4000-8000-000000000001/papers/d0a80123-0000-4000-8000-000000000002"')
  })
})

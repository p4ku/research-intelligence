import type { AuditQueueItem } from '@/lib/bff/audit/schema'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { AuditTable } from './audit-table'

const sampleItems: AuditQueueItem[] = [
  {
    cohort_id: 'c0a80123-0000-4000-8000-000000000001',
    pipeline_run_id: 'f0a80123-0000-4000-8000-000000000001',
    workspace_id: 'e0a80123-0000-4000-8000-000000000001',
    workspace_name: 'Lassa Fever Virus (WHO Priority)',
    briefing_name: 'Lassa Fever Transmission Dynamics SLR',
    gate: 'full_text_screening',
    assigned_count: 10,
    completed_count: 4,
    remaining_count: 6,
    status: 'in_review',
    created_at: '2026-10-20T10:00:00Z',
  },
  {
    cohort_id: 'c0a80123-0000-4000-8000-000000000002',
    pipeline_run_id: 'f0a80123-0000-4000-8000-000000000002',
    workspace_id: 'e0a80123-0000-4000-8000-000000000002',
    workspace_name: 'Oncology Therapeutics',
    briefing_name: 'EGFR Mutation NSCLC Systematic Review',
    gate: 'abstract_screening',
    assigned_count: 20,
    completed_count: 0,
    remaining_count: 20,
    status: 'pending',
    created_at: '2026-10-21T08:00:00Z',
  },
  {
    cohort_id: 'c0a80123-0000-4000-8000-000000000003',
    pipeline_run_id: 'f0a80123-0000-4000-8000-000000000003',
    workspace_id: 'e0a80123-0000-4000-8000-000000000003',
    workspace_name: 'Cardiology Studies',
    briefing_name: 'SGLT2 Inhibitor HFpEF Review',
    gate: 'parameter_extraction',
    assigned_count: 5,
    completed_count: 5,
    remaining_count: 0,
    status: 'completed',
    created_at: '2026-10-19T12:00:00Z',
  },
]

describe('AuditTable Component Rendering', () => {
  test('renders audit table with correct columns and gate labels', () => {
    const html = renderToStaticMarkup(<AuditTable items={sampleItems} />)

    // Table header titles
    expect(html).toContain('Briefing / Workspace')
    expect(html).toContain('Pipeline Run')
    expect(html).toContain('Audit Gate')
    expect(html).toContain('Progress')
    expect(html).toContain('Remaining')
    expect(html).toContain('Status')
    expect(html).toContain('Action')

    // Briefing and workspace details
    expect(html).toContain('Lassa Fever Transmission Dynamics SLR')
    expect(html).toContain('Lassa Fever Virus (WHO Priority)')
    expect(html).toContain('Full-text screening')

    // Truncated pipeline run id
    expect(html).toContain('run-f0a80123')

    // Progress numbers
    expect(html).toContain('4/10')
    expect(html).toContain('40%')

    // Status pill
    expect(html).toContain('In review')

    // Action button points to cohort
    expect(html).toContain('href="/audit-queue/c0a80123-0000-4000-8000-000000000001"')
    expect(html).toContain('Review →')
  })

  test('renders tab headers with accurate counts', () => {
    const html = renderToStaticMarkup(<AuditTable items={sampleItems} />)

    // 2 pending/in-review, 3 all, 1 completed
    expect(html).toContain('My Pending (2)')
    expect(html).toContain('All Assigned (3)')
    expect(html).toContain('Completed History (1)')
  })

  test('renders empty state when queue items list is empty', () => {
    const html = renderToStaticMarkup(<AuditTable items={[]} />)

    expect(html).toContain('No pending audits assigned to you.')
    expect(html).toContain('My Pending (0)')
    expect(html).toContain('All Assigned (0)')
  })
})

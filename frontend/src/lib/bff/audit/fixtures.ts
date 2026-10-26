import type {
  AuditCohortDetail,
  AuditPaperDetail,
  AuditQueueItem,
  AuditReviewResult,
} from './schema'

export const mockCohortId1 = 'c0a80123-0000-4000-8000-000000000001'
export const mockCohortId2 = 'c0a80123-0000-4000-8000-000000000002'
export const mockPaperId1 = 'd0a80123-0000-4000-8000-000000000001'
export const mockPaperId2 = 'd0a80123-0000-4000-8000-000000000002'
export const mockWorkspaceId1 = 'e0a80123-0000-4000-8000-000000000001'
export const mockRunId1 = 'f0a80123-0000-4000-8000-000000000001'

export const mockQueueItems: AuditQueueItem[] = [
  {
    cohort_id: mockCohortId1,
    pipeline_run_id: mockRunId1,
    workspace_id: mockWorkspaceId1,
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
    cohort_id: mockCohortId2,
    pipeline_run_id: 'f0a80123-0000-4000-8000-000000000002',
    workspace_id: mockWorkspaceId1,
    workspace_name: 'Ebola Vaccine Trial SLR',
    briefing_name: 'Ebola Phase III Safety & Efficacy',
    gate: 'full_text_screening',
    assigned_count: 15,
    completed_count: 0,
    remaining_count: 15,
    status: 'pending',
    created_at: '2026-10-20T14:30:00Z',
  },
]

export const mockPaperDetail1: AuditPaperDetail = {
  paper_id: mockPaperId1,
  cohort_id: mockCohortId1,
  title: 'Geographical drivers and climate-linked dynamics of Lassa fever in Nigeria',
  authors: 'David W. Redding, Rory Gibb, Chioma C. Dan-Nwafor, et al.',
  journal: 'Nature Communications',
  publication_year: 2021,
  doi: '10.1038/s41467-021-25910-y',
  pdf_url: `/api/papers/${mockPaperId1}/pdf/`,
  has_full_text: true,
  abstract:
    'Lassa fever is an acute viral haemorrhagic illness endemic in parts of West Africa. We analysed rodent reservoir host distributions, transmission parameters, and climate correlates across Nigeria...',
  ai_decision: 'include',
  ai_confidence: 0.94,
  ai_reasoning:
    'Study presents primary clinical and epidemiological data on Lassa virus infection in humans with confirmed case fatality ratios (CFR) and empirical basic reproduction number (R0) estimates in endemic Nigerian LGAs.',
  matched_criteria: [
    'Lassa virus / Arenaviridae',
    'Human transmission data',
    'Extractable parameters (R0, CFR)',
    'English full-text available',
  ],
  evidence_quotes: [
    {
      quote:
        'We estimated a basic reproduction number R0 of 1.34 (95% CI 1.12-1.61) across affected local government areas (LGAs) during the 2018–2020 seasonal outbreaks.',
      page_number: 3,
      section: 'Transmission Dynamics and Parameter Fitting',
    },
    {
      quote:
        'Among hospitalized cases with confirmed RT-PCR diagnosis, the overall in-hospital case fatality ratio was 21.4% (32/150).',
      page_number: 5,
      section: 'Clinical Manifestation and Outcomes',
    },
  ],
  is_reviewed: false,
  reviewer_decision: null,
  exclusion_reason: null,
  reviewer_note: null,
  evidence_citation: null,
  reviewed_at: null,
  current_index: 5,
  total_count: 10,
  prev_paper_id: 'd0a80123-0000-4000-8000-000000000004',
  next_paper_id: mockPaperId2,
  extractions: [
    {
      extraction_id: 'a0a80123-0000-4000-8000-000000000001',
      category: 'epidemiology',
      parameter_name: 'Basic Reproduction Number (R0)',
      extracted_value: '1.34',
      uncertainty: '95% CI (1.12 - 1.61)',
      method: 'Maximum Likelihood (Empirical)',
      text_evidence:
        'We estimated a basic reproduction number R0 of 1.34 (95% CI 1.12-1.61) across affected local government areas.',
      page_number: 3,
      status: 'pending',
    },
    {
      extraction_id: 'a0a80123-0000-4000-8000-000000000002',
      category: 'clinical',
      parameter_name: 'Case Fatality Ratio (CFR)',
      extracted_value: '21.4% (32 / 150)',
      uncertainty: 'Denominator: 150 cases',
      method: 'In-hospital confirmed RT-PCR cohort',
      text_evidence:
        'Among hospitalized cases with confirmed RT-PCR diagnosis, the overall in-hospital case fatality ratio was 21.4% (32/150).',
      page_number: 5,
      status: 'pending',
    },
  ],
}

export const mockCohortDetail1: AuditCohortDetail = {
  cohort_id: mockCohortId1,
  pipeline_run_id: mockRunId1,
  stage: 'full_text_screening',
  is_audit_complete: false,
  total_papers: 10,
  completed_count: 4,
  first_unreviewed_paper_id: mockPaperId1,
  papers: [
    {
      paper_id: 'd0a80123-0000-4000-8000-000000000000',
      index: 1,
      title: 'Epidemiology of Lassa Fever in Edo State',
      doi: '10.1016/j.ijid.2020.01.001',
      is_reviewed: true,
    },
    {
      paper_id: mockPaperId1,
      index: 5,
      title: 'Geographical drivers and climate-linked dynamics of Lassa fever in Nigeria',
      doi: '10.1038/s41467-021-25910-y',
      is_reviewed: false,
    },
    {
      paper_id: mockPaperId2,
      index: 6,
      title: 'Genomic Surveillance of Lassa Virus During the 2018 Outbreak',
      doi: '10.1056/NEJMoa1804498',
      is_reviewed: false,
    },
  ],
}

export const mockReviewResult: AuditReviewResult = {
  status: 'reviewed',
  review_id: 'e0a80123-9999-4000-8000-000000000001',
  decision: 'include',
  is_cohort_complete: false,
  next_unreviewed_paper_id: mockPaperId2,
  pipeline_resumed: false,
}

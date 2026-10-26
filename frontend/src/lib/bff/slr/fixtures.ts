import type { SLRDispute, SLRPipelineRunItem, SLRPRISMAMetrics, SLRROBAssessment } from './schema'

export const mockSLRRuns: SLRPipelineRunItem[] = [
  {
    id: 'a2a44548-6af3-47ce-a538-724427e69e0b',
    name: 'Deep Learning Benchmarks & Clinical Transformers SLR',
    workspace_id: '73df18b9-a897-4074-bf41-c51fca1aa5d6',
    workspace_name: 'clinical_ai_slr',
    status: 'completed',
    created_at: '2026-10-26T21:45:00Z',
  },
  {
    id: 'f0a80123-0000-4000-8000-000000000001',
    name: 'Viral Pathogen Transmission Models Meta-Analysis',
    workspace_id: 'c0a80123-0000-4000-8000-000000000001',
    workspace_name: 'epidemiology_models',
    status: 'paused_at_checkpoint_gate',
    created_at: '2026-10-26T20:30:00Z',
  },
]

export const mockPrismaMetrics: SLRPRISMAMetrics = {
  id: '555b3465-fbc6-4f6a-b5df-2cfce1c4dc84',
  pipeline_run: 'a2a44548-6af3-47ce-a538-724427e69e0b',
  records_identified_total: 480,
  records_by_source: {
    pubmed: 260,
    arxiv: 140,
    openalex: 80,
  },
  duplicates_removed: 42,
  records_screened_abstract: 438,
  records_excluded_abstract: 320,
  abstract_exclusion_reasons: {
    'Wrong Pathogen / Topic': 210,
    'Non-English Language': 45,
    'Animal Study Only': 38,
    'No Extractable Parameters': 27,
  },
  full_text_assessed: 118,
  full_text_excluded: 86,
  full_text_exclusion_reasons: {
    'Absent Empirical Methodology': 44,
    'Missing Control Cohort': 26,
    'In-Vitro Only (No Transmission)': 16,
  },
  studies_included_synthesis: 32,
  studies_included_meta_analysis: 24,
  human_inter_rater_kappa: 0.88,
  ai_vs_human_kappa: 0.84,
  ai_sensitivity: 0.965,
  ai_specificity: 0.923,
  generated_at: '2026-10-26T22:00:00Z',
}

export const mockRobAssessments: SLRROBAssessment[] = [
  {
    id: 'rob-001',
    paper: 'p-001',
    paper_title: 'Attention Is All You Need in Clinical Prognosis',
    pipeline_run: 'a2a44548-6af3-47ce-a538-724427e69e0b',
    framework: 'rob2',
    domain_scores: {
      D1_randomization: {
        rating: 'low_risk',
        quote: 'Patients were randomized 1:1 using computer-generated blocks.',
        page: 3,
      },
      D2_deviations: {
        rating: 'low_risk',
        quote: 'Double-blind protocol preserved across all treatment arms.',
        page: 4,
      },
      D3_missing_data: {
        rating: 'low_risk',
        quote: 'Complete case follow-up exceeded 98.5% at endpoint.',
        page: 6,
      },
      D4_measurement: {
        rating: 'low_risk',
        quote: 'Blinded central pathology review confirmed all primary endpoints.',
        page: 8,
      },
      D5_selection: {
        rating: 'low_risk',
        quote: 'Pre-registered clinical trial protocol matched analysis plan verbatim.',
        page: 11,
      },
    },
    overall_bias: 'low_risk',
    traffic_light_color: 'green',
    is_human_verified: true,
    human_notes:
      'Pristine multicenter randomized clinical trial with negligible risk across all domains.',
  },
  {
    id: 'rob-002',
    paper: 'p-002',
    paper_title: 'Evaluating Diffusion Transformers on Retrospective Cohorts',
    pipeline_run: 'a2a44548-6af3-47ce-a538-724427e69e0b',
    framework: 'rob2',
    domain_scores: {
      D1_randomization: {
        rating: 'some_concerns',
        quote: 'Allocation sequence generation details were not explicitly stated.',
        page: 4,
      },
      D2_deviations: {
        rating: 'low_risk',
        quote: 'No significant protocol deviations recorded during observational phase.',
        page: 5,
      },
      D3_missing_data: {
        rating: 'some_concerns',
        quote: '14% attrition observed in the secondary subgroup without imputation.',
        page: 9,
      },
      D4_measurement: {
        rating: 'low_risk',
        quote: 'Automated diagnostic logging ensured standardized outcome capture.',
        page: 7,
      },
      D5_selection: {
        rating: 'low_risk',
        quote: 'Outcomes reported consistent with initial trial registry.',
        page: 12,
      },
    },
    overall_bias: 'some_concerns',
    traffic_light_color: 'yellow',
    is_human_verified: false,
    human_notes: 'Moderate risk due to omitted randomization specifics and sub-cohort attrition.',
  },
  {
    id: 'rob-003',
    paper: 'p-003',
    paper_title: 'Uncalibrated Neural Estimators in Emergency Triage',
    pipeline_run: 'a2a44548-6af3-47ce-a538-724427e69e0b',
    framework: 'rob2',
    domain_scores: {
      D1_randomization: {
        rating: 'high_risk',
        quote: 'Pseudorandom allocation alternating by odd/even admission dates.',
        page: 2,
      },
      D2_deviations: {
        rating: 'some_concerns',
        quote: 'Clinicians were unblinded to triage recommendations.',
        page: 5,
      },
      D3_missing_data: {
        rating: 'high_risk',
        quote: 'Over 28% of patient discharge forms lacked follow-up telemetry.',
        page: 8,
      },
      D4_measurement: {
        rating: 'some_concerns',
        quote: 'Subjective clinician assessment utilized for borderline outcomes.',
        page: 6,
      },
      D5_selection: {
        rating: 'high_risk',
        quote: 'Post-hoc subgroup metrics reported without pre-specified hypothesis.',
        page: 14,
      },
    },
    overall_bias: 'high_risk',
    traffic_light_color: 'red',
    is_human_verified: true,
    human_notes:
      'High risk of bias: allocation predictable, severe attrition and uncalibrated post-hoc reporting.',
  },
]

export const mockDisputes: SLRDispute[] = [
  {
    id: 'disp-001',
    sample_cohort: 'c0a80123-0000-4000-8000-000000000001',
    paper: 'paper-disp-001',
    paper_title: 'Mathematical Modeling of Zoonotic Spillover in Sub-Saharan Enclaves',
    paper_doi: '10.1038/s41564-023-01452-1',
    stage: 'abstract',
    status: 'pending',
    arbiter: null,
    final_decision: null,
    final_exclusion_reason: null,
    resolution_rationale: null,
    evidence_synthesis: {
      reviewer_1: {
        reviewer_name: 'Dr. Anna Kowalska',
        decision: 'include',
        notes:
          'Contains formal compartmental ODE system with basic reproduction number (R0) derivations.',
        quotes: [
          'We formulate an SEIR-V transmission framework parametrized with empirical field telemetry.',
        ],
      },
      reviewer_2: {
        reviewer_name: 'Dr. John Smith',
        decision: 'exclude',
        exclusion_reason: 'Solely Animal Study (No Transmission Parameters)',
        notes:
          'Sampling limited to bat reservoir populations; human epidemiological transmission was not measured.',
        quotes: ['Sera collected exclusively from Eidolon helvum frugivorous bats.'],
      },
      ai_agent: {
        decision: 'include',
        confidence: 0.74,
        reasoning:
          'The manuscript presents numerical parameter estimations of spillover potential matching criteria.',
      },
    },
    created_at: '2026-10-26T21:10:00Z',
    resolved_at: null,
  },
  {
    id: 'disp-002',
    sample_cohort: 'c0a80123-0000-4000-8000-000000000001',
    paper: 'paper-disp-002',
    paper_title: 'Genomic Surveillance of Multi-Drug Resistant Hospital Strains',
    paper_doi: '10.1016/S1473-3099(23)00412-9',
    stage: 'full_text',
    status: 'resolved',
    arbiter: 1,
    final_decision: 'exclude',
    final_exclusion_reason: 'No Extractable Parameters / Models',
    resolution_rationale:
      'Binding Senior Arbiter ruling: Study strictly tracks phylogenetic trees without reporting clinical intervention parameters or transmission dynamics coefficients.',
    evidence_synthesis: {
      reviewer_1: {
        reviewer_name: 'Dr. Anna Kowalska',
        decision: 'include',
        notes: 'Good empirical sequencing data across 500 isolates.',
        quotes: ['Whole genome sequencing performed on 512 Klebsiella isolates.'],
      },
      reviewer_2: {
        reviewer_name: 'Dr. John Smith',
        decision: 'exclude',
        exclusion_reason: 'No Extractable Parameters / Models',
        notes: 'Pure phylogenetic taxonomy without mechanistic modeling.',
        quotes: ['No transmission rate or kinetic parameters were estimated.'],
      },
      ai_agent: {
        decision: 'exclude',
        confidence: 0.89,
        reasoning: 'Absence of quantitative epidemic modeling or transmission risk ratios.',
      },
    },
    created_at: '2026-10-26T20:15:00Z',
    resolved_at: '2026-10-26T21:40:00Z',
  },
]

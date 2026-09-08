import { describe, expect, test } from 'bun:test'
import * as z from 'zod'
import { workspace } from '../workspaces/schema'
import {
  dimension,
  dimensionFacet,
  dimensionField,
  dimensionList,
  riskAndAffiliation,
  riskFlag,
  scoredPaper,
  signalScoreDetails,
} from './schema'

/**
 * Realistic payload structure emitted by Django's:
 * - GET /api/papers/{id}/scorecard/?pipeline_run=...
 * - GET /api/workspaces/{id}/scorecard/?run_id=...
 */
const mockRawPaperPayload = {
  id: '00000000-0000-4000-8000-000000000041',
  workspace_id: '00000000-0000-4000-8000-000000000001',
  pipeline_run_id: '00000000-0000-4000-8000-000000000031',
  pipeline_run_name: 'Hybrid AI Quantum Scan - Run #42',
  title: 'Dynamic Intermediate Representation for Hybrid Quantum-Classical Programs',
  authors: ['Alex Rice', 'Chris Heunen', 'Tobias Grosser'],
  authors_raw: 'Alex Rice, Chris Heunen, Tobias Grosser',
  abstract:
    'Quantum compilers typically follow the circuit model. We introduce an IR that elevates gates to first-class values.',
  doi: '10.1145/3611643.3616281',
  arxiv_id: '2609.01037',
  source: 'arxiv',
  screening_status: 'full_text_passed',
  screening_reasoning: 'Proposes an intermediate representation directly addressing hybrid quantum workflows.',
  abstract_screening_reasoning: 'Passed abstract evaluation: novel quantum IR.',
  full_text_screening_reasoning: 'Passed full text review: solid empirical benchmarks on Qiskit and LLVM.',
  signal_score: 84.6,
  signal_score_details: {
    variables: {
      trl_level: 4,
      scientific_novelty: 88,
      ecosystem_fit: 82,
      gdpr_compliant: true,
    },
    code_snippet: 'score = 0.5 * ecosystem_fit + 0.3 * scientific_novelty + 0.2 * (trl_level * 10)',
    calculated_at: '2026-09-08T22:30:00Z',
    error: null,
  },
  dimensions: [
    {
      key: 'trl_level',
      definition_id: '00000000-0000-4000-8000-000000000011',
      name: 'TRL Level',
      label: 'Technology Readiness Level',
      value: 4,
      raw: 'TRL 4',
      max: 9,
      is_trl: true,
      is_risk_and_affiliation: false,
      has_postprocessing: true,
      band: 'TRL 4 — Technology validated in lab',
      rationale:
        'The compiler framework was prototyped and verified on synthetic quantum-classical benchmark circuits in a laboratory environment.',
      evidence: [
        '“We evaluate our IR across a suite of 14 hybrid quantum-classical algorithms.”',
        '“Demonstrated 2.4x speedup in circuit synthesis on simulation backends.”',
      ],
      confidence: 0.95,
      validation_status: 'valid',
      review_required: false,
      model: 'google/gemini-3.8-flash',
      primary_metric: {
        key: 'trl_level',
        value: 4,
        numeric_value: 4,
        is_numeric: true,
      },
      secondary_metrics: [
        {
          key: 'confidence',
          value: 0.95,
          numeric_value: 0.95,
          is_numeric: true,
        },
        {
          key: 'simulation_passed',
          value: true,
          numeric_value: null,
          is_numeric: false,
        },
      ],
      facets: [
        {
          key: 'confidence',
          name: 'Confidence',
          value: 0.95,
          max: 1,
          text: 'High confidence based on detailed experimental sections in paper.',
        },
        {
          key: 'benchmark_score',
          name: 'Benchmark score',
          value: 78,
          max: 100,
          text: null,
        },
      ],
      texts: [
        {
          key: 'experimental_methodology',
          name: 'Experimental methodology',
          value: 'Tested against standard Qiskit runtime using simulated noisy intermediate-scale quantum devices.',
        },
      ],
      lists: [
        {
          key: 'validated_use_cases',
          name: 'Validated use cases',
          items: [
            'Variational Quantum Eigensolver (VQE) feedback loop',
            'Quantum Approximate Optimization Algorithm (QAOA) parameter tuning',
          ],
        },
      ],
      facts: [
        { key: 'reproducible_code', name: 'Reproducible code', value: true },
        { key: 'target_hardware', name: 'Target hardware', value: 'Trapped ion & superconducting qubits' },
      ],
    },
    {
      key: 'scientific_novelty',
      definition_id: '00000000-0000-4000-8000-000000000012',
      name: 'Scientific Novelty',
      label: 'Scientific Novelty',
      value: 88,
      raw: '88/100',
      max: 100,
      is_trl: false,
      is_risk_and_affiliation: false,
      has_postprocessing: false,
      band: 'High Novelty',
      rationale: 'First unified IR treating quantum gates as first-class citizens in classical SSA representation.',
      evidence: ['“To our knowledge, this is the first SSA-form IR with dynamic gate composition.”'],
      confidence: 0.9,
      model: 'google/gemini-3.8-flash',
      facets: [],
      texts: [],
      lists: [],
      facts: [],
    },
  ],
  pdf_key: 'papers/a1b2c3d4/paper.pdf',
  markdown_key: 'papers/a1b2c3d4/paper.md',
  source_url: 'https://arxiv.org/abs/2609.01037',
  is_benchmark: true,
  evaluation_label: 'passed',
  published_date: '2026-09-01',
  created_at: '2026-09-08T22:00:00Z',
  risk_and_affiliation: {
    affiliations: ['University of Edinburgh', 'TU Munich'],
    author_contacts: ['alex.rice@ed.ac.uk', 'grosser@in.tum.de'],
    funding_entities: ['European Research Council (ERC)', 'UKRI Quantum Hub'],
    codebase_artifact_link: 'https://github.com/hybrid-quantum/dynamic-ir',
    schwarz_ecosystem_affiliation: 'no',
    gdpr_concerns: 'no',
    competitor_involvement: 'none',
    risk_score: 12,
    risk_score_assessment: 'Low overall risk',
    flags: [
      {
        key: 'gdpr',
        label: 'GDPR Sovereignty',
        value: 'no',
        status: 'safe',
      },
      {
        key: 'schwarz_ecosystem',
        label: 'Schwarz Ecosystem',
        value: 'no',
        status: 'neutral',
      },
      {
        key: 'competitor',
        label: 'Competitor Involvement',
        value: 'none',
        status: 'safe',
      },
    ],
  },
}

const mockWorkspacePayload = {
  id: '00000000-0000-4000-8000-000000000001',
  name: 'Quantum Hybrid Computing',
  user_role: 'researcher',
  definitions: [
    {
      id: '00000000-0000-4000-8000-000000000011',
      name: 'TRL Level',
      key: 'trl_level',
      is_active: true,
      is_trl: true,
      max: 9,
    },
  ],
  scrapers: [],
  digest_schedule: '0 8 * * *',
  screening_llm_model: 'google/gemini-3.8-flash',
  llm_provider: 'google',
  created_at: '2026-09-01T00:00:00Z',
}

describe('Scorecard data flow through stack contracts', () => {
  test('scoredPaper schema validates full raw Django paper scorecard payload', () => {
    const parsed = scoredPaper.safeParse(mockRawPaperPayload)
    expect(parsed.success).toBe(true)
    if (!parsed.success) return

    const paper = parsed.data
    expect(paper.title).toBe(mockRawPaperPayload.title)
    expect(paper.signal_score).toBe(84.6)
    expect(paper.is_benchmark).toBe(true)
    expect(paper.evaluation_label).toBe('passed')
    expect(paper.dimensions).toHaveLength(2)
  })

  test('signalScoreDetails validates variable types, formula snippet and error field', () => {
    const details = signalScoreDetails.parse(mockRawPaperPayload.signal_score_details)
    expect(details.variables.trl_level).toBe(4)
    expect(details.variables.gdpr_compliant).toBe(true)
    expect(details.code_snippet).toContain('ecosystem_fit')
    expect(details.error).toBeNull()
  })

  test('dimension extracts validate rich visual structures: band, facets, texts, lists, facts, evidence', () => {
    const trlDim = dimension.parse(mockRawPaperPayload.dimensions[0])
    expect(trlDim.is_trl).toBe(true)
    expect(trlDim.band).toBe('TRL 4 — Technology validated in lab')
    expect(trlDim.confidence).toBe(0.95)
    expect(trlDim.has_postprocessing).toBe(true)

    // Facets
    expect(trlDim.facets).toHaveLength(2)
    const confFacet = dimensionFacet.parse(trlDim.facets![0])
    expect(confFacet.name).toBe('Confidence')
    expect(confFacet.value).toBe(0.95)
    expect(confFacet.max).toBe(1)
    expect(confFacet.text).toContain('High confidence')

    // Texts
    expect(trlDim.texts).toHaveLength(1)
    const textEntry = dimensionField.parse(trlDim.texts![0])
    expect(textEntry.name).toBe('Experimental methodology')
    expect(textEntry.value).toContain('Qiskit runtime')

    // Lists
    expect(trlDim.lists).toHaveLength(1)
    const listEntry = dimensionList.parse(trlDim.lists![0])
    expect(listEntry.name).toBe('Validated use cases')
    expect(listEntry.items).toHaveLength(2)

    // Facts
    expect(trlDim.facts).toHaveLength(2)
    const factEntry = dimensionField.parse(trlDim.facts![0])
    expect(factEntry.name).toBe('Reproducible code')
    expect(factEntry.value).toBe(true)

    // Evidence quotes
    expect(trlDim.evidence).toHaveLength(2)
    expect(trlDim.evidence![0]).toContain('suite of 14 hybrid')
  })

  test('riskAndAffiliation schema parses affiliations, contacts, code link, and flags', () => {
    const risk = riskAndAffiliation.parse(mockRawPaperPayload.risk_and_affiliation)
    expect(risk.affiliations).toEqual(['University of Edinburgh', 'TU Munich'])
    expect(risk.author_contacts).toEqual(['alex.rice@ed.ac.uk', 'grosser@in.tum.de'])
    expect(risk.funding_entities).toContain('European Research Council (ERC)')
    expect(risk.codebase_artifact_link).toBe('https://github.com/hybrid-quantum/dynamic-ir')
    expect(risk.risk_score).toBe(12)
    expect(risk.risk_score_assessment).toBe('Low overall risk')

    expect(risk.flags).toHaveLength(3)
    const gdprFlag = riskFlag.parse(risk.flags[0])
    expect(gdprFlag.label).toBe('GDPR Sovereignty')
    expect(gdprFlag.status).toBe('safe')
  })

  test('workspaceScorecardResponse validates workspace and list of scored papers', () => {
    const workspaceScorecardResponse = z.object({
      workspace,
      papers: z.array(scoredPaper),
    })

    const payload = {
      workspace: mockWorkspacePayload,
      papers: [mockRawPaperPayload],
    }

    const parsed = workspaceScorecardResponse.safeParse(payload)
    expect(parsed.success).toBe(true)
    if (!parsed.success) return

    expect(parsed.data.workspace.name).toBe('Quantum Hybrid Computing')
    expect(parsed.data.papers).toHaveLength(1)
    expect(parsed.data.papers[0].id).toBe(mockRawPaperPayload.id)
  })

  test('detailResponse validates single paper scorecard endpoint response', () => {
    const detailResponse = z.object({
      workspace,
      paper: scoredPaper,
    })

    const payload = {
      workspace: mockWorkspacePayload,
      paper: mockRawPaperPayload,
    }

    const parsed = detailResponse.safeParse(payload)
    expect(parsed.success).toBe(true)
    if (!parsed.success) return

    expect(parsed.data.paper.title).toBe(mockRawPaperPayload.title)
    expect(parsed.data.paper.signal_score).toBe(84.6)
  })
})

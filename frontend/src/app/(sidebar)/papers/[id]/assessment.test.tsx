import { makeT } from '@/lib/i18n'
import type { Dimension } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { Assessment, definitionAnchor } from './assessment'

const t = makeT('en')

describe('Assessment Component Rendering', () => {
  const fullDimension: Dimension = {
    key: 'trl_level',
    definition_id: '00000000-0000-4000-8000-000000000011',
    name: 'TRL Level',
    value: 4,
    raw: 'TRL 4',
    max: 9,
    is_trl: true,
    has_postprocessing: true,
    band: 'TRL 4 — Technology validated in lab',
    rationale: 'Comprehensive benchmark evaluation across multiple simulator backends.',
    confidence: 0.92,
    model: 'google/gemini-3.8-flash',
    validation_status: 'valid',
    review_required: false,
    facets: [
      {
        key: 'confidence_score',
        name: 'Confidence score',
        value: 0.92,
        max: 1,
        text: 'Direct empirical results reported with standard deviations.',
      },
      {
        key: 'speedup_ratio',
        name: 'Speedup ratio',
        value: 2.4,
        max: 5,
        text: null,
      },
    ],
    texts: [
      {
        key: 'hardware_target_notes',
        name: 'Hardware target notes',
        value: 'Targeted at gate-model quantum processors with classical coprocessors.',
      },
    ],
    lists: [
      {
        key: 'core_contributions',
        name: 'Core contributions',
        items: [
          'Dynamic gate creation as first-class SSA values',
          'Hybrid loop-pipelining compiler optimization',
        ],
      },
    ],
    evidence: [
      '“Our intermediate representation reduces circuit compilation latency by 58%.”',
      '“Validated on 14 hybrid benchmark programs.”',
    ],
    facts: [
      { key: 'open_source', name: 'Open source', value: true },
      { key: 'quantum_backend', name: 'Quantum backend', value: 'Qiskit & Cirq' },
    ],
  }

  const riskDimension: Dimension = {
    key: 'risk_and_affiliation',
    definition_id: null,
    name: 'Risk and Affiliation',
    value: null,
    raw: '—',
    max: null,
    is_trl: false,
    is_risk_and_affiliation: true,
    rationale: 'Should not appear in Assessment list',
  }

  test('renders definition header, anchor id, band badge, and headline value', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    const anchor = definitionAnchor(fullDimension)

    expect(out).toContain(`id="${anchor}"`)
    expect(out).toContain('TRL Level')
    expect(out).toContain('TRL 4 — Technology validated in lab')
    expect(out).toContain('4')
    expect(out).toContain('/9') // max is 9
  })

  test('renders rationale markdown prose', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Comprehensive benchmark evaluation across multiple simulator backends.')
  })

  test('omits rationale placeholder when rationale is absent or null', () => {
    const dimWithoutRationale = { ...fullDimension, rationale: null }
    const out = renderToStaticMarkup(<Assessment dimensions={[dimWithoutRationale]} t={t} />)
    expect(out).not.toContain('No rationale recorded.')
  })

  test('renders facets with progress fill and twin assessment notes', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Confidence score')
    expect(out).toContain('0.92')
    expect(out).toContain('Direct empirical results reported with standard deviations.')
    expect(out).toContain('Speedup ratio')
    expect(out).toContain('2.4')
    // Facet progress scaleX
    expect(out).toContain('scaleX(')
  })

  test('renders titled texts sections', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Hardware target notes')
    expect(out).toContain('Targeted at gate-model quantum processors with classical coprocessors.')
  })

  test('renders bulleted lists with item contents', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Core contributions')
    expect(out).toContain('Dynamic gate creation as first-class SSA values')
    expect(out).toContain('Hybrid loop-pipelining compiler optimization')
  })

  test('renders evidence quotes unquoted within blockquote tags', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('<blockquote')
    expect(out).toContain(
      'Our intermediate representation reduces circuit compilation latency by 58%.',
    )
    expect(out).toContain('Validated on 14 hybrid benchmark programs.')
  })

  test('renders facts key-value pairs and converts booleans to Yes/No', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Open source')
    expect(out).toContain('Yes')
    expect(out).toContain('Quantum backend')
    expect(out).toContain('Qiskit &amp; Cirq')
  })

  test('does not render bottom metadata (confidence, model, badges) under definitions', () => {
    const hitlDim: Dimension = {
      ...fullDimension,
      is_hitl: true,
      has_postprocessing: true,
      validation_status: 'warn',
      confidence: 0.92,
      model: 'google/gemini-3.8-flash',
    }
    const out = renderToStaticMarkup(<Assessment dimensions={[hitlDim]} t={t} />)
    expect(out).not.toContain('Confidence 92%')
    expect(out).not.toContain('Gemini 3.8 Flash')
    expect(out).not.toContain('Rule verified')
    expect(out).not.toContain('Human verified')
    expect(out).not.toContain('Needs review')
  })

  test('filters out risk and affiliation dimensions from the Assessment article list', () => {
    const out = renderToStaticMarkup(
      <Assessment dimensions={[fullDimension, riskDimension]} t={t} />,
    )
    expect(out).toContain('TRL Level')
    expect(out).not.toContain('Should not appear in Assessment list')
  })

  test('renders fallback copy when no visible dimensions are provided', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[]} t={t} />)
    expect(out).toContain('Not scored yet')
  })

  test('unpacks stringified dictionary submetrics (Novelty band, insight, quotes) without duplicating score', () => {
    const dictDimension: Dimension = {
      key: 'research_metrics',
      definition_id: '11111111-1111-1111-1111-111111111111',
      name: 'Research Metrics',
      value: 68,
      raw: '68',
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'novelty',
          name: 'Novelty',
          value: 68,
          max: 100,
          text: null,
          band: 'Substantial',
        },
      ],
      texts: [
        {
          key: 'novelty',
          name: 'Novelty',
          value:
            "{'band': 'Substantial', 'score': 68, 'insight': 'The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.', 'evidence': ['quantum-assisted framework for PDE-based Bayesian inverse problems', 'hybrid quantum-classical algorithm using quantum linear system algorithms (QLSAs)']}",
        },
      ],
      evidence: [],
      facts: [],
      lists: [],
    }
    const out = renderToStaticMarkup(<Assessment dimensions={[dictDimension]} t={t} />)
    expect(out).toContain('Research Metrics')
    expect(out).toContain('Substantial')
    expect(out).toContain(
      'The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.',
    )
    expect(out).toContain('“quantum-assisted framework for PDE-based Bayesian inverse problems”')
    expect(out).toContain(
      '“hybrid quantum-classical algorithm using quantum linear system algorithms (QLSAs)”',
    )
    expect(out).not.toContain("{'band'")
    expect(out).not.toContain("'score': 68")
  })

  test('renders structured dictionary submetric when backend marks type as dict', () => {
    const structuredDimension: Dimension = {
      key: 'research_metrics',
      definition_id: '11111111-1111-1111-1111-111111111111',
      name: 'Research Metrics',
      value: 68,
      raw: '68',
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'novelty',
          name: 'Novelty',
          value: 68,
          max: 100,
          text: null,
          band: 'Substantial',
        },
      ],
      texts: [
        {
          key: 'novelty',
          name: 'Novelty',
          type: 'dict',
          is_dict: true,
          band: 'Substantial',
          score: 68,
          insight:
            'The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.',
          evidence: [
            'quantum-assisted framework for PDE-based Bayesian inverse problems',
            'hybrid quantum-classical algorithm using quantum linear system algorithms (QLSAs)',
          ],
          dict_value: {
            band: 'Substantial',
            score: 68,
            insight:
              'The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.',
            evidence: [
              'quantum-assisted framework for PDE-based Bayesian inverse problems',
              'hybrid quantum-classical algorithm using quantum linear system algorithms (QLSAs)',
            ],
          },
          value:
            'The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.',
        },
      ],
      evidence: [],
      facts: [],
      lists: [],
    }
    const out = renderToStaticMarkup(<Assessment dimensions={[structuredDimension]} t={t} />)
    expect(out).toContain('data-type="submetric-dict"')
    expect(out).toContain('Substantial')
    expect(out).toContain('Sub-score: 68')
    expect(out).toContain('Evidence')
    expect(out).toContain(
      'The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.',
    )
    expect(out).toContain('“quantum-assisted framework for PDE-based Bayesian inverse problems”')
  })

  test('unifies duplicate submetrics across facets and texts into a single sequential block with progress bar, insight, and quotes', () => {
    const stagingLikeDim: Dimension = {
      key: 'research_metrics',
      definition_id: '11111111-1111-1111-1111-111111111111',
      name: 'Research Metrics',
      value: 68,
      raw: '68',
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'novelty',
          name: 'Novelty',
          value: 68,
          max: 100,
          text: 'The paper introduces a substantial new framing...',
          band: 'Substantial',
        },
        {
          key: 'significance',
          name: 'Significance',
          value: 62,
          max: 100,
          text: 'This work addresses a prominent bottleneck...',
          band: 'Important',
        },
        {
          key: 'rigour',
          name: 'Rigour',
          value: 65,
          max: 100,
          text: 'The authors provide a mathematically sound formulation...',
          band: 'Sound',
        },
        { key: 'rigour_score', name: 'Rigour', value: 65, max: 100, text: null },
        { key: 'novelty_score', name: 'Novelty', value: 68, max: 100, text: null },
        { key: 'significance_score', name: 'Significance', value: 62, max: 100, text: null },
      ],
      texts: [
        {
          key: 'rigour',
          name: 'Rigour',
          type: 'dict',
          is_dict: true,
          band: 'Sound',
          score: 65,
          insight: 'The authors provide a mathematically sound formulation...',
          evidence: [
            'rigorous complexity analysis establishing conditions for end-to-end quantum speedup',
          ],
          value: 'The authors provide a mathematically sound formulation...',
        },
        {
          key: 'novelty',
          name: 'Novelty',
          type: 'dict',
          is_dict: true,
          band: 'Substantial',
          score: 68,
          insight: 'The paper introduces a substantial new framing...',
          evidence: ['quantum-assisted framework for PDE-based Bayesian inverse problems'],
          value: 'The paper introduces a substantial new framing...',
        },
        {
          key: 'significance',
          name: 'Significance',
          type: 'dict',
          is_dict: true,
          band: 'Important',
          score: 62,
          insight: 'This work addresses a prominent bottleneck...',
          evidence: ['mitigates the cubic complexity barrier in large-scale inverse problems'],
          value: 'This work addresses a prominent bottleneck...',
        },
      ],
      evidence: [],
      facts: [],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[stagingLikeDim]} t={t} />)
    // Exactly 3 sub-metric blocks rendered (not 6, not 9!)
    const noveltyMatches = out.match(/data-submetric="novelty"/g) ?? []
    expect(noveltyMatches.length).toBe(1)
    const rigourMatches = out.match(/data-submetric="rigour"/g) ?? []
    expect(rigourMatches.length).toBe(1)
    const significanceMatches = out.match(/data-submetric="significance"/g) ?? []
    expect(significanceMatches.length).toBe(1)

    // Progress bar fill scaleX is present for each
    expect(out).toContain('scaleX(0.68)')
    expect(out).toContain('scaleX(0.62)')
    expect(out).toContain('scaleX(0.65)')

    // Evidence quotes are present within the sub-metric
    expect(out).toContain(
      '“rigorous complexity analysis establishing conditions for end-to-end quantum speedup”',
    )
    expect(out).toContain('“quantum-assisted framework for PDE-based Bayesian inverse problems”')
    expect(out).toContain(
      '“mitigates the cubic complexity barrier in large-scale inverse problems”',
    )
  })

  test('applies dynamic schema titles, descriptions, and maximums to sub-measures and prose texts', () => {
    const schemaDimension: Dimension = {
      key: 'quantum_advantage',
      definition_id: '22222222-2222-2222-2222-222222222222',
      name: 'Quantum Advantage',
      value: 8,
      raw: '8',
      max: 10,
      is_trl: false,
      response_schema: {
        type: 'object',
        properties: {
          fidelity: {
            type: 'number',
            title: 'Physical Qubit Fidelity',
            description: 'Two-qubit gate benchmark fidelity across simulator backends',
            minimum: 0,
            maximum: 10,
          },
          novelty: {
            type: 'object',
            title: 'Novelty Assessment',
            description: 'Algorithmic novelty and theoretical speedup over classical baselines',
            properties: {
              score: { type: 'number', maximum: 10 },
            },
          },
          hardware_notes: {
            type: 'string',
            title: 'Hardware Architecture Notes',
            description: 'Specific superconducting processor requirements',
          },
        },
      },
      facets: [
        {
          key: 'fidelity',
          name: 'fidelity',
          value: 8.5,
          max: 100, // facet max was 100, schema maximum is 10
          text: 'Benchmark completed on noisy simulator.',
        },
      ],
      texts: [
        {
          key: 'novelty',
          name: 'novelty',
          type: 'dict',
          is_dict: true,
          score: 7,
          value: 'Introduces a new tensor contraction ordering.',
          dict_value: {
            score: 7,
            insight: 'Introduces a new tensor contraction ordering.',
          },
        },
        {
          key: 'hardware_notes',
          name: 'hardware_notes',
          value: 'Requires at least 64 physical transmon qubits with all-to-all connectivity.',
        },
      ],
      evidence: [],
      facts: [],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[schemaDimension]} t={t} />)

    // Title from schema replaces raw key
    expect(out).toContain('Physical Qubit Fidelity')
    expect(out).toContain('Novelty Assessment')
    expect(out).toContain('Hardware Architecture Notes')

    // Description from schema rendered as subtitle/caption
    expect(out).toContain('Two-qubit gate benchmark fidelity across simulator backends')
    expect(out).toContain('Algorithmic novelty and theoretical speedup over classical baselines')
    expect(out).toContain('Specific superconducting processor requirements')

    // Maximum from schema (10, not 100) used for fidelity progress bar (8.5 / 10 = 0.85)
    expect(out).toContain('scaleX(0.85)')
  })
})

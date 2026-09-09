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

  test('omits Confidence feature (e.g. Confidence: HIGH) under TRL section', () => {
    const trlDim: Dimension = {
      ...fullDimension,
      key: 'trl_level',
      name: 'Technology Readiness Level (TRL)',
      is_trl: true,
      facets: [],
      texts: [
        {
          key: 'core_technology',
          name: 'Core technology',
          value: 'Hardware accelerator architecture for Zero-Knowledge Proofs.',
        },
      ],
      facts: [
        { key: 'confidence', name: 'Confidence', value: 'HIGH' },
        { key: 'hardware_target', name: 'Hardware target', value: 'FPGA' },
      ],
    }
    const out = renderToStaticMarkup(<Assessment dimensions={[trlDim]} t={t} />)
    expect(out).toContain('Technology being Assessed')
    expect(out).toContain('Hardware target')
    expect(out).not.toContain('Confidence')
    expect(out).not.toContain('HIGH')
  })

  test('renames Core Technology subtitle to Technology being Assessed, removes grey description, and removes extra bottom border', () => {
    const trlDim: Dimension = {
      ...fullDimension,
      key: 'trl_level',
      name: 'Technology Readiness Level (TRL)',
      is_trl: true,
      response_schema: {
        type: 'object',
        properties: {
          core_technology: {
            type: 'string',
            title: 'Core technology',
            description: 'The technology being assessed.',
          },
        },
      },
      texts: [
        {
          key: 'core_technology',
          name: 'Core technology',
          value:
            'Hardware-algorithm co-designed accelerator architecture and algorithmic optimizations for fully homomorphic encryption (FHE)',
        },
      ],
      facets: [],
      facts: [],
    }
    const out = renderToStaticMarkup(<Assessment dimensions={[trlDim]} t={t} />)
    expect(out).toContain('Technology being Assessed')
    expect(out).not.toContain('Core technology')
    expect(out).not.toContain('The technology being assessed.')
    expect(out).toContain('last:border-b-0')
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
    // Assessment pill (band) removed from sub-measures per design update
    expect(out).not.toContain('<span class="rounded-sm')
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
    // Assessment pill (band) removed from sub-measures per design update
    expect(out).not.toContain('<span class="rounded-sm')
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

    // Sub-measure descriptions removed to prevent duplicate grey text under score dimensions
    expect(out).not.toContain('Two-qubit gate benchmark fidelity across simulator backends')
    expect(out).not.toContain(
      'Algorithmic novelty and theoretical speedup over classical baselines',
    )
    // Prose text description is preserved
    expect(out).toContain('Specific superconducting processor requirements')

    // Maximum from schema (10, not 100) used for fidelity progress bar (8.5 / 10 = 0.85)
    expect(out).toContain('scaleX(0.85)')
  })

  test('renders no number or dash next to definition name when primary metric is null, and keeps all 3 submetrics', () => {
    // User's exact bug case: "Research Metrics" without primary metric, but with novelty (68), significance (65), rigour (72)
    const researchMetricsDim: Dimension = {
      key: 'research_metrics',
      definition_id: '00000000-0000-4000-8000-000000000099',
      name: 'Research Metrics',
      value: null,
      raw: null as unknown as string,
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'novelty',
          name: 'Novelty',
          value: 68,
          max: 100,
          text: 'Novel framing and architecture.',
        },
        {
          key: 'significance',
          name: 'Significance',
          value: 65,
          max: 100,
          text: 'Addresses hybrid quantum optimization.',
        },
        {
          key: 'rigour',
          name: 'Rigour',
          value: 72,
          max: 100,
          text: 'Extensive empirical benchmarks.',
        },
      ],
      texts: [],
      evidence: [],
      facts: [],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[researchMetricsDim]} t={t} />)

    // Definition title is rendered
    expect(out).toContain('Research Metrics')

    // Header MUST NOT contain any headline number or dash next to the title
    const headerMatch = out.match(/<header[^>]*>([\s\S]*?)<\/header>/)
    expect(headerMatch).not.toBeNull()
    const headerContent = headerMatch![1]
    expect(headerContent).toContain('Research Metrics')
    expect(headerContent).not.toContain('68')
    expect(headerContent).not.toContain('—')

    // All 3 submetrics MUST be rendered with their respective scores
    expect(out).toContain('Novelty')
    expect(out).toContain('68')
    expect(out).toContain('Significance')
    expect(out).toContain('65')
    expect(out).toContain('Rigour')
    expect(out).toContain('72')
  })

  test('renders headline score and no submeasures when definition has primary metric but no secondaries', () => {
    // Case 2: Solo primary metric (e.g. Fit Score = 88) with no secondaries
    const soloPrimaryDim: Dimension = {
      key: 'fit_score',
      definition_id: '00000000-0000-4000-8000-000000000098',
      name: 'Fit Score',
      value: 88,
      raw: '88',
      max: 100,
      is_trl: false,
      facets: [],
      texts: [],
      evidence: [],
      facts: [],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[soloPrimaryDim]} t={t} />)

    // Header has the score 88
    const headerMatch = out.match(/<header[^>]*>([\s\S]*?)<\/header>/)
    expect(headerMatch).not.toBeNull()
    expect(headerMatch![1]).toContain('Fit Score')
    expect(headerMatch![1]).toContain('88')

    // No submetric rows rendered
    expect(out).not.toContain('data-submetric')
  })

  test('does not render assessment pill (band) or duplicate grey description under score dimensions, keeping responsive grid', () => {
    const dim: Dimension = {
      key: 'research_metrics',
      definition_id: '00000000-0000-4000-8000-000000000001',
      name: 'Research Metrics',
      value: 68,
      raw: '68',
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'rigour',
          name: 'Rigour',
          value: 74,
          max: 100,
          text: 'The research provides formal mathematical proofs...',
          band: 'Sound',
        },
        {
          key: 'novelty',
          name: 'Novelty',
          value: 68,
          max: 100,
          text: 'The work innovatively challenges prevailing cryptographic conventions...',
          band: 'Substantial',
        },
        {
          key: 'significance',
          name: 'Significance',
          value: 73,
          max: 100,
          text: 'Breaking the sub-millisecond bootstrapping threshold...',
          band: 'Important',
        },
      ],
      texts: [],
      evidence: [],
      facts: [],
      lists: [],
      response_schema: {
        properties: {
          rigour: {
            title: 'Rigour',
            description: 'Rigour assessment',
          },
          novelty: {
            title: 'Novelty',
            description: 'Novelty assessment',
          },
          significance: {
            title: 'Significance',
            description: 'Significance assessment',
          },
        },
      },
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[dim]} t={t} />)
    // Submetric titles and scores are present
    expect(out).toContain('Rigour')
    expect(out).toContain('74')
    expect(out).toContain('Novelty')
    expect(out).toContain('68')
    expect(out).toContain('Significance')
    expect(out).toContain('73')

    // Duplicate grey descriptions under submetrics are removed
    expect(out).not.toContain('Rigour assessment')
    expect(out).not.toContain('Novelty assessment')
    expect(out).not.toContain('Significance assessment')

    // Assessment pills (Sound, Substantial, Important badges) are removed
    expect(out).not.toContain('Sound')
    expect(out).not.toContain('Substantial')
    expect(out).not.toContain('Important')

    // Responsive grid classes are present
    expect(out).toContain('grid-cols-[minmax(0,1fr)_44px] sm:grid-cols-[200px_minmax(0,1fr)_44px]')
  })

  test('moves Research Quality Insight and Schwarz Fit Insight text boxes to the top under section headers without subtitle', () => {
    const researchMetricsWithInsight: Dimension = {
      key: 'research_metrics',
      definition_id: '00000000-0000-4000-8000-000000000002',
      name: 'Research Metrics',
      value: 68,
      raw: '68',
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'rigour',
          name: 'Rigour',
          value: 74,
          max: 100,
          text: 'Rigour text details...',
        },
        {
          key: 'novelty',
          name: 'Novelty',
          value: 68,
          max: 100,
          text: 'Novelty text details...',
        },
      ],
      texts: [
        {
          key: 'research_quality_insight',
          name: 'Research quality insight',
          value:
            'The paper excels in its cross-layer co-design, demonstrating that rethinking mathematical algorithm parameters yields dramatic hardware utilization gains.',
        },
        {
          key: 'hardware_architecture_notes',
          name: 'Hardware Architecture Notes',
          value: 'Requires at least 64 physical qubits.',
        },
      ],
      evidence: [],
      facts: [],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[researchMetricsWithInsight]} t={t} />)

    // 1. The insight text content IS rendered
    expect(out).toContain(
      'The paper excels in its cross-layer co-design, demonstrating that rethinking mathematical algorithm parameters yields dramatic hardware utilization gains.',
    )

    // 2. The subtitle / heading "Research quality insight" is REMOVED
    expect(out).not.toContain('Research quality insight')
    expect(out).not.toContain('Research Quality Insight')

    // 3. The insight text appears BEFORE the submeasures in the DOM
    const insightIdx = out.indexOf('The paper excels in its cross-layer co-design')
    const submeasureIdx = out.indexOf('data-submetric="rigour"')
    const remainingTextIdx = out.indexOf('Hardware Architecture Notes')

    expect(insightIdx).toBeGreaterThan(0)
    expect(submeasureIdx).toBeGreaterThan(insightIdx)
    expect(remainingTextIdx).toBeGreaterThan(submeasureIdx)

    // 4. Non-insight general prose text still keeps its h4 heading
    expect(out).toContain(
      '<h4 class="text-sm font-semibold text-zinc-950 dark:text-white">Hardware Architecture Notes</h4>',
    )
  })

  test('omits duplicate sub-measure scores from facts at the bottom of scoring dimensions', () => {
    // User case: backend emits rigour_score, novelty_score, significance_score in facts
    const dimWithDuplicateFacts: Dimension = {
      key: 'research_metrics',
      definition_id: '00000000-0000-4000-8000-000000000003',
      name: 'Research Metrics',
      value: 68,
      raw: '68',
      max: 100,
      is_trl: false,
      facets: [
        { key: 'novelty', name: 'Novelty', value: 68, max: 100, text: 'Novelty text' },
        {
          key: 'significance',
          name: 'Significance',
          value: 73,
          max: 100,
          text: 'Significance text',
        },
        { key: 'rigour', name: 'Rigour', value: 74, max: 100, text: 'Rigour text' },
      ],
      texts: [],
      evidence: [],
      facts: [
        { key: 'rigour_score', name: 'Rigour', value: '74' },
        { key: 'novelty_score', name: 'Novelty', value: '68' },
        { key: 'significance_score', name: 'Significance', value: '73' },
        { key: 'independent_fact', name: 'Compute Architecture', value: 'GPU + FPGA' },
      ],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[dimWithDuplicateFacts]} t={t} />)

    // Independent fact is kept
    expect(out).toContain('Compute Architecture')
    expect(out).toContain('GPU + FPGA')

    // Facts DL does NOT contain duplicate submeasure items
    const dlMatch = out.match(/<dl[^>]*>([\s\S]*?)<\/dl>/)
    expect(dlMatch).not.toBeNull()
    const dlContent = dlMatch![1]
    expect(dlContent).not.toContain('Rigour')
    expect(dlContent).not.toContain('Novelty')
    expect(dlContent).not.toContain('Significance')
  })

  test('moves Schwarz Fit Insight from facts to the top under section header without subtitle', () => {
    // User img 2 case: Schwarz fit insight delivered in facts
    const schwarzFitDim: Dimension = {
      key: 'schwarz_fit',
      definition_id: '00000000-0000-4000-8000-000000000004',
      name: 'Schwarz Fit',
      value: 64,
      raw: '64',
      max: 100,
      is_trl: false,
      facets: [
        {
          key: 'strategic_operational_need',
          name: 'Strategic operational need',
          value: 78,
          max: 100,
        },
        {
          key: 'cross_industry_scalability',
          name: 'Cross industry scalability',
          value: 82,
          max: 100,
        },
      ],
      texts: [],
      evidence: [],
      facts: [
        {
          key: 'schwarz_fit_insight',
          name: 'Schwarz fit insight',
          value:
            'WHET aligns strongly with Schwarz Digits sovereign cloud strategy and external market offerings for privacy-preserving AI.',
        },
      ],
      lists: [],
    }

    const out = renderToStaticMarkup(<Assessment dimensions={[schwarzFitDim]} t={t} />)

    // 1. Rendered at the top
    expect(out).toContain(
      'WHET aligns strongly with Schwarz Digits sovereign cloud strategy and external market offerings for privacy-preserving AI.',
    )

    // 2. Subtitle / heading "Schwarz fit insight" is omitted
    expect(out).not.toContain('Schwarz fit insight')

    // 3. No <dl> left for facts since the only fact was an insight
    expect(out).not.toContain('<dl')

    // 4. Insight is placed BEFORE submeasure rows
    const insightIdx = out.indexOf('WHET aligns strongly with Schwarz Digits')
    const submeasureIdx = out.indexOf('data-submetric="strategic_operational_need"')
    expect(insightIdx).toBeGreaterThan(0)
    expect(submeasureIdx).toBeGreaterThan(insightIdx)
  })
})

import type { ExtractionDTO, ExtractionDefinitionDTO, PaperDTO } from '@/lib/api/types'
import { describe, expect, test } from 'bun:test'
import {
  arxivId,
  arxivIdOf,
  corpusMaxima,
  definitionContexts,
  doiOf,
  httpUrl,
  humaniseKey,
  inferScale,
  oneLine,
  parseNumeric,
  pickMetric,
  resolveExitMetric,
  sanitizeIdentifier,
  splitAuthors,
  toScoredPaper,
} from './map'

describe('sanitizeIdentifier (parity with scorer._sanitize_identifier)', () => {
  test('cases from the backend docstring', () => {
    expect(sanitizeIdentifier('TRL Level')).toBe('trl_level')
    expect(sanitizeIdentifier('Fit-Score (0-100)')).toBe('fit_score_0_100')
    expect(sanitizeIdentifier('  Novelty  ')).toBe('novelty')
    expect(sanitizeIdentifier('2nd Opinion')).toBe('v_2nd_opinion')
    expect(sanitizeIdentifier('')).toBe('param')
    expect(sanitizeIdentifier('___')).toBe('param')
  })
})

describe('parseNumeric (parity with scorer._parse_numeric_value, null instead of 0)', () => {
  test('numbers and numeric strings', () => {
    expect(parseNumeric(4)).toBe(4)
    expect(parseNumeric('7')).toBe(7)
    expect(parseNumeric(' 8.5 ')).toBe(8.5)
  })
  test('units and prefixes', () => {
    expect(parseNumeric('TRL 4')).toBe(4)
    expect(parseNumeric('Score: 8.5')).toBe(8.5)
    expect(parseNumeric('85%')).toBe(0.85)
    expect(parseNumeric('9.5 / 10')).toBe(9.5)
  })
  test('nested field objects', () => {
    expect(parseNumeric({ value: 24.5, confidence: 0.9 })).toBe(24.5)
    expect(parseNumeric({ value: null, normalized_value: '24.5%' })).toBe(0.245)
  })
  test('non-numeric is null, not zero', () => {
    expect(parseNumeric('High')).toBeNull()
    expect(parseNumeric('')).toBeNull()
    expect(parseNumeric('-')).toBeNull()
    expect(parseNumeric(null)).toBeNull()
    expect(parseNumeric(true)).toBeNull()
  })
})

describe('resolveExitMetric (tiers 2–3 of Extraction.exit_metric)', () => {
  test('flat form keyed by the definition name', () => {
    expect(resolveExitMetric({ trl_level: 'TRL 3' }, 'TRL Level', 'TRL Level')).toEqual({
      raw: 'TRL 3',
      matchedKey: 'trl_level',
    })
    expect(resolveExitMetric({ fit_score: '5' }, 'Fit Score', 'Fit Score').raw).toBe('5')
  })
  test('strips _score / _extraction suffixes when matching', () => {
    expect(resolveExitMetric({ novelty: 4 }, 'Novelty Score', 'Novelty Score').raw).toBe('4')
  })
  test('nested form with value objects', () => {
    const data = {
      fields: {
        efficiency: {
          value: 24.5,
          normalized_value: '24.5%',
          confidence: 0.95,
          evidence: [{ quote: 'achieved 24.5% PCE', rationale: 'Direct claim' }],
        },
      },
    }
    expect(resolveExitMetric(data, 'Efficiency', 'Efficiency')).toEqual({
      raw: '24.5',
      matchedKey: 'efficiency',
    })
  })
  test('falls back to the first short scalar', () => {
    expect(
      resolveExitMetric(
        { url: 'http://example.com', reasoning: 'x'.repeat(100), score: 7 },
        'Other',
        'Other',
      ),
    ).toEqual({ raw: '7', matchedKey: 'score' })
  })
  test('empty payload', () => {
    expect(resolveExitMetric(null, 'A', 'A').raw).toBe('-')
    expect(resolveExitMetric({}, 'A', 'A').raw).toBe('-')
  })
})

describe('inferScale', () => {
  const def = (
    name: string,
    prompt = '',
  ): Pick<ExtractionDefinitionDTO, 'name' | 'system_prompt'> => ({
    name,
    system_prompt: prompt,
  })
  test('TRL is always 1–9', () => expect(inferScale(def('TRL Level'), 3)).toBe(9))
  test('range hint in the prompt wins', () => {
    expect(inferScale(def('Fit Score', 'Extract relevance fit (1-10)'), 5)).toBe(10)
    expect(inferScale(def('Fit-Score (0-100)'), 5)).toBe(100)
  })
  test('otherwise from the corpus maximum', () => {
    expect(inferScale(def('Novelty'), 4)).toBe(10)
    expect(inferScale(def('Novelty'), 83)).toBe(100)
    expect(inferScale(def('Novelty'), 830)).toBeNull()
    expect(inferScale(def('Novelty'), null)).toBeNull()
  })
})

describe('splitAuthors', () => {
  test('comma, semicolon, and "and"', () => {
    expect(splitAuthors('Alice Quantum, Bob Beginner and Carol Chen')).toEqual([
      'Alice Quantum',
      'Bob Beginner',
      'Carol Chen',
    ])
    expect(splitAuthors('')).toEqual([])
  })
})

describe('oneLine', () => {
  test("collapses the source's line wrap", () => {
    // Exactly how arXiv's Atom feed hands us this title.
    expect(
      oneLine('PennyLane: Automatic differentiation of hybrid quantum-classical\n  computations'),
    ).toBe('PennyLane: Automatic differentiation of hybrid quantum-classical computations')
    // The arXiv XML parser's own output: newline swapped for a space, indent kept.
    expect(oneLine('hybrid quantum-classical   computations')).toBe(
      'hybrid quantum-classical computations',
    )
    expect(oneLine('  padded\ttitle \n')).toBe('padded title')
    expect(oneLine(null)).toBe('')
  })
  test('keeps a no-break space — that is typography, not a wrap', () => {
    expect(oneLine('Fig. 1 at 10 kg')).toBe('Fig. 1 at 10 kg')
  })
  test('collapses the wrap when it arrives escaped — backslash and letter, two characters', () => {
    // Exactly what OpenAlex serves for W4289606390. One escaped wrap before
    // whitespace or the end marks the field; every one in it then collapses.
    expect(
      oneLine('PennyLane: Automatic differentiation of hybrid quantum-classical\\n computations'),
    ).toBe('PennyLane: Automatic differentiation of hybrid quantum-classical computations')
    expect(oneLine('programming of\\nquantum computers.\\n')).toBe(
      'programming of quantum computers.',
    )
    expect(oneLine('line one\\r\\nline two\\r\\n')).toBe('line one line two')
    // TeX's own doubled backslash is never a wrap, even in a marked field.
    expect(oneLine('row one \\\\newline two\\n')).toBe('row one \\\\newline two')
  })
  test('keeps TeX — no mark, so every backslash stays', () => {
    expect(oneLine('$q=\\nabla u$ yields')).toBe('$q=\\nabla u$ yields')
    // Real abstracts carry TeX with no $ around it.
    expect(oneLine('We propose RISE (\\textbf{R}efining \\textit{I}magination)')).toBe(
      'We propose RISE (\\textbf{R}efining \\textit{I}magination)',
    )
    expect(oneLine('Assuming $P\\neq NP$, we\\nestablish')).toBe(
      'Assuming $P\\neq NP$, we\\nestablish',
    )
    expect(oneLine('$\\texttt{DisMorph}$: learning\n  to disentangle')).toBe(
      '$\\texttt{DisMorph}$: learning to disentangle',
    )
  })
})

/* -------------------------- composition fixtures --------------------------- */

const defs: ExtractionDefinitionDTO[] = [
  {
    id: 'def-fit',
    name: 'Fit Score',
    system_prompt: 'Extract relevance fit (1-10)',
    user_prompt_template: '{paper_text}',
    response_schema: {},
    llm_model: 'google/gemini-3.8-flash',
    is_active: true,
    created_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 'def-nov',
    name: 'Novelty Score',
    system_prompt: 'Extract novelty (1-10)',
    user_prompt_template: '{paper_text}',
    response_schema: {},
    llm_model: 'google/gemini-3.8-flash',
    is_active: true,
    created_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 'def-trl',
    name: 'TRL Level',
    system_prompt: 'Extract TRL level (1-9)',
    user_prompt_template: '{paper_text}',
    response_schema: {},
    llm_model: 'google/gemini-3.8-flash',
    is_active: true,
    created_at: '2026-08-01T00:00:00Z',
  },
]

function extraction(
  partial: Partial<ExtractionDTO> & Pick<ExtractionDTO, 'id' | 'paper'>,
): ExtractionDTO {
  return {
    workspace: 'ws-1',
    extraction_definition: null,
    category: '',
    fields_data: {},
    is_hitl_validated: false,
    version_info: {},
    validation_status: 'pending',
    review_required: false,
    confidence_score: null,
    confidence_method: null,
    created_at: '2026-08-02T00:00:00Z',
    ...partial,
  }
}

function paper(partial: Partial<PaperDTO> & Pick<PaperDTO, 'id'>): PaperDTO {
  return {
    workspace: 'ws-1',
    pipeline_run: 'run-1',
    hash_id: 'h',
    doi: null,
    arxiv_id: null,
    title: 'T',
    authors: 'A. Author, B. Author',
    abstract: 'abs',
    source_database: 'arxiv',
    original_pdf_path: null,
    converted_md_path: null,
    screening_status: 'full_text_passed',
    screening_reasoning: null,
    is_evaluation_benchmark: false,
    evaluation_label: null,
    metrics: [],
    created_at: '2026-08-02T00:00:00Z',
    ...partial,
  }
}

describe('toScoredPaper', () => {
  const exts: ExtractionDTO[] = [
    extraction({
      id: 'e1',
      paper: 'p1',
      extraction_definition: 'def-fit',
      category: 'Fit Score',
      fields_data: { fit_score: '5' },
    }),
    extraction({
      id: 'e2',
      paper: 'p1',
      extraction_definition: 'def-nov',
      category: 'Novelty Score',
      fields_data: { novelty_score: 'High' },
    }),
    extraction({
      id: 'e3',
      paper: 'p1',
      extraction_definition: 'def-trl',
      category: 'TRL Level',
      fields_data: {
        trl_level: 'TRL 3',
        reasoning: 'Lab validation only.',
        evidence_quotes: ['distance-3 surface code'],
      },
    }),
  ]
  const contexts = definitionContexts(defs, corpusMaxima(defs, exts))

  test('arxivId normalises a real id and rejects a leaked OpenAlex W-id', () => {
    expect(arxivId('2402.11111')).toBe('2402.11111')
    expect(arxivId(' arXiv:2402.11111v2 ')).toBe('2402.11111v2')
    expect(arxivId('cond-mat.mes-hall/0703029')).toBe('cond-mat.mes-hall/0703029')
    expect(arxivId('W2781738013')).toBeNull()
    expect(arxivId('2402.111')).toBeNull()
    expect(arxivId(null)).toBeNull()
  })

  test('arxivIdOf / doiOf read the link, shape-checked, query and fragment aside', () => {
    expect(arxivIdOf('https://arxiv.org/abs/cond-mat/0102536')).toBe('cond-mat/0102536')
    expect(arxivIdOf('http://export.arxiv.org/abs/2402.11111v3?context=cs#top')).toBe(
      '2402.11111v3',
    )
    expect(arxivIdOf('https://arxiv.org/abs/2402.11111/')).toBe('2402.11111')
    // The backend's backfill of a leaked W-id: a 404 that must not read "arXiv".
    expect(arxivIdOf('https://arxiv.org/abs/W2781738013')).toBeNull()
    expect(arxivIdOf('https://arxiv.org/pdf/2402.11111.pdf')).toBeNull()
    expect(arxivIdOf('https://doi.org/10.1/x')).toBeNull()
    expect(doiOf('https://doi.org/10.1/x')).toBe('10.1/x')
    expect(doiOf('https://dx.doi.org/10.1000/abc#frag')).toBe('10.1000/abc')
    expect(doiOf('https://doi.org/10.1000/a%3Cb')).toBe('10.1000/a<b')
    expect(doiOf('https://doi.org/')).toBeNull()
    expect(doiOf('not a url')).toBeNull()
    expect(doiOf(null)).toBeNull()
  })

  test('httpUrl lets only http(s) through to an href', () => {
    expect(httpUrl('https://openalex.org/W1')).toBe('https://openalex.org/W1')
    expect(httpUrl('HTTP://x.org/')).toBe('HTTP://x.org/')
    expect(httpUrl('javascript:alert(1)')).toBeNull()
    expect(httpUrl('data:text/html,hi')).toBeNull()
    expect(httpUrl('')).toBeNull()
    expect(httpUrl(null)).toBeNull()
  })

  test('source_url is the backend value; never rebuilt from the ids', () => {
    const doi = toScoredPaper(
      paper({ id: 'p2', doi: '10.1/x', source_url: 'https://doi.org/10.1/x' }),
      [],
      contexts,
    )
    expect(doi.source_url).toBe('https://doi.org/10.1/x')
    // A replay captured before the column existed, with a W-id in arxiv_id.
    const stale = toScoredPaper(paper({ id: 'p3', arxiv_id: 'W2781738013' }), [], contexts)
    expect(stale.source_url).toBeNull()
    const none = toScoredPaper(paper({ id: 'p4', source_url: null }), [], contexts)
    expect(none.source_url).toBeNull()
    const unsafe = toScoredPaper(paper({ id: 'p5', source_url: 'javascript:1' }), [], contexts)
    expect(unsafe.source_url).toBeNull()
  })

  test('dimension values, rationale, and evidence from flat fields', () => {
    const p = toScoredPaper(
      paper({
        id: 'p1',
        arxiv_id: '2402.11111',
        source_url: 'https://arxiv.org/abs/2402.11111',
        metrics: [
          {
            id: 'm1',
            paper: 'p1',
            pipeline_run: 'run-1',
            workspace: 'ws-1',
            signal_score: 95.5,
            signal_score_details: {
              variables: { fit_score: 5, novelty_score: 0, trl_level: 3 },
              code_snippet: 'return 95.5',
              score: 95.5,
              calculated_at: 'x',
              error: null,
            },
            metrics_data: { fit_score: 5, novelty_score: 'High', trl_level: 3 },
            created_at: '2026-08-02T00:00:00Z',
          },
        ],
      }),
      exts,
      contexts,
    )
    expect(p.signal_score).toBe(95.5)
    expect(p.source_url).toBe('https://arxiv.org/abs/2402.11111')
    expect(p.authors).toEqual(['A. Author', 'B. Author'])
    const [fit, nov, trl] = p.dimensions
    expect(fit).toMatchObject({ key: 'fit_score', value: 5, raw: '5', max: 10 })
    expect(nov).toMatchObject({ key: 'novelty_score', value: null, raw: 'High' })
    expect(trl).toMatchObject({
      key: 'trl_level',
      value: 3,
      max: 9,
      is_trl: true,
      rationale: 'Lab validation only.',
    })
    expect(trl.evidence).toEqual(['distance-3 surface code'])
  })

  test('title and abstract arrive single-lined, whatever the source stored', () => {
    const p = toScoredPaper(
      paper({
        id: 'p-wrap',
        title: 'PennyLane: Automatic differentiation of hybrid quantum-classical\n  computations',
        abstract: 'PennyLane is a Python 3 software framework for\ndifferentiable programming.',
      }),
      [],
      contexts,
    )
    expect(p.title).toBe(
      'PennyLane: Automatic differentiation of hybrid quantum-classical computations',
    )
    expect(p.abstract).toBe(
      'PennyLane is a Python 3 software framework for differentiable programming.',
    )
  })

  test('no extraction row → null value even when metrics_data pre-fills 0.0', () => {
    const p = toScoredPaper(
      paper({
        id: 'p2',
        metrics: [
          {
            id: 'm2',
            paper: 'p2',
            pipeline_run: 'run-1',
            workspace: 'ws-1',
            signal_score: 12,
            signal_score_details: {},
            metrics_data: { fit_score: 0.0, novelty_score: 0.0, trl_level: 0.0 },
            created_at: '2026-08-02T00:00:00Z',
          },
        ],
      }),
      [],
      contexts,
    )
    expect(p.dimensions.map((d) => d.value)).toEqual([null, null, null])
    expect(p.dimensions.map((d) => d.raw)).toEqual(['—', '—', '—'])
    expect(p.signal_score_details).toBeNull()
  })

  test('pre-filled 0.0 metric never overrides a non-numeric extraction (null, not 0)', () => {
    const highOnly: ExtractionDTO[] = [
      extraction({
        id: 'e9',
        paper: 'p3',
        extraction_definition: 'def-nov',
        category: 'Novelty Score',
        fields_data: { novelty_score: 'High' },
      }),
    ]
    const p = toScoredPaper(
      paper({
        id: 'p3',
        metrics: [
          {
            id: 'm3',
            paper: 'p3',
            pipeline_run: 'run-1',
            workspace: 'ws-1',
            signal_score: 40,
            signal_score_details: {},
            metrics_data: { fit_score: 0.0, novelty_score: 0.0, trl_level: 0.0 },
            created_at: '2026-08-02T00:00:00Z',
          },
        ],
      }),
      highOnly,
      contexts,
    )
    const nov = p.dimensions.find((d) => d.key === 'novelty_score')!
    expect(nov.value).toBeNull()
    expect(nov.raw).toBe('High')
  })

  test('a computed non-zero metric still outranks a non-numeric raw', () => {
    const highOnly: ExtractionDTO[] = [
      extraction({
        id: 'e10',
        paper: 'p4',
        extraction_definition: 'def-nov',
        category: 'Novelty Score',
        fields_data: { novelty_score: 'High' },
      }),
    ]
    const p = toScoredPaper(
      paper({
        id: 'p4',
        metrics: [
          {
            id: 'm4',
            paper: 'p4',
            pipeline_run: 'run-1',
            workspace: 'ws-1',
            signal_score: 40,
            signal_score_details: {},
            metrics_data: { novelty_score: 8 },
            created_at: '2026-08-02T00:00:00Z',
          },
        ],
      }),
      highOnly,
      contexts,
    )
    expect(p.dimensions.find((d) => d.key === 'novelty_score')!.value).toBe(8)
  })

  test('unscored paper', () => {
    const p = toScoredPaper(paper({ id: 'p3', screening_status: 'weird' }), [], contexts)
    expect(p.signal_score).toBeNull()
    expect(p.screening_status).toBe('pending')
  })

  test('nested field form carries confidence and evidence', () => {
    const nested = extraction({
      id: 'e9',
      paper: 'p4',
      extraction_definition: 'def-fit',
      category: 'Fit Score',
      fields_data: {
        fields: {
          fit_score: {
            value: 8,
            confidence: 0.95,
            evidence: [{ quote: 'strong retail relevance', rationale: 'Direct claim' }],
          },
        },
      },
    })
    const p = toScoredPaper(paper({ id: 'p4' }), [nested], contexts)
    expect(p.dimensions[0]).toMatchObject({ value: 8, confidence: 0.95, rationale: 'Direct claim' })
    expect(p.dimensions[0].evidence).toEqual(['strong retail relevance'])
  })
})

describe('pickMetric', () => {
  test('prefers the paper’s own run, else newest', () => {
    const p = paper({
      id: 'p',
      pipeline_run: 'run-2',
      metrics: [
        {
          id: 'a',
          paper: 'p',
          pipeline_run: 'run-1',
          workspace: 'w',
          signal_score: 1,
          signal_score_details: {},
          metrics_data: {},
          created_at: '2026-01-01',
        },
        {
          id: 'b',
          paper: 'p',
          pipeline_run: 'run-2',
          workspace: 'w',
          signal_score: 2,
          signal_score_details: {},
          metrics_data: {},
          created_at: '2025-01-01',
        },
      ],
    })
    expect(pickMetric(p)?.id).toBe('b')
    expect(pickMetric({ ...p, pipeline_run: 'run-9' })?.id).toBe('a')
    expect(pickMetric({ ...p, metrics: [] })).toBeNull()
  })
})

describe('definition detail (the rest of the payload, shaped by its keys)', () => {
  const contexts = definitionContexts(defs, corpusMaxima(defs, []))

  test('humaniseKey reads a key as a name, acronyms upper-cased', () => {
    expect(humaniseKey('need_match_score')).toBe('Need match')
    expect(humaniseKey('stackit_sovereignty_score')).toBe('STACKIT sovereignty')
    expect(humaniseKey('market_width_assessment')).toBe('Market width')
    expect(humaniseKey('evidence_of_movement')).toBe('Evidence of movement')
  })

  test('facets with their assessment twins, lists, prose, facts; duplicates dropped', () => {
    const fit = extraction({
      id: 'e-fit',
      paper: 'p-d',
      extraction_definition: 'def-fit',
      category: 'Fit Score',
      exit_metric: '25.1',
      version_info: { llm_model: 'google/gemini-3.8-flash' },
      fields_data: {
        fit_score: 25.1,
        justification: 'Low fit: quantum chemistry, not retail.',
        need_match_score: 10,
        fit_score_computed: 25.1,
        market_width_score: 22,
        need_match_assessment: 'No retail relevance.',
        fit_score_postprocessed: 25.1,
        market_width_assessment: 'Narrow.',
        schwarz_fit_computed: 25.1,
        vendor_lockin_risks: ['IBM cloud backend', ''],
        interconnect_protocol: 'OpenMPI',
        containerization_feasibility: 'H'.repeat(120),
        limitations_acknowledged: true,
      },
    })
    const p = toScoredPaper(paper({ id: 'p-d' }), [fit], contexts)
    const d = p.dimensions[0]!
    expect(d).toMatchObject({ value: 25.1, raw: '25.1', max: 10, model: 'google/gemini-3.8-flash' })
    expect(d.rationale).toBe('Low fit: quantum chemistry, not retail.')
    expect(d.band).toBeUndefined()
    expect(d.facets).toEqual([
      {
        key: 'need_match_score',
        name: 'Need match',
        value: 10,
        max: 10,
        text: 'No retail relevance.',
      },
      { key: 'market_width_score', name: 'Market width', value: 22, max: 10, text: 'Narrow.' },
    ])
    expect(d.lists).toEqual([
      { key: 'vendor_lockin_risks', name: 'Vendor lockin risks', items: ['IBM cloud backend'] },
    ])
    expect(d.texts).toEqual([
      {
        key: 'containerization_feasibility',
        name: 'Containerization feasibility',
        value: 'H'.repeat(120),
      },
    ])
    expect(d.facts).toEqual([
      { key: 'interconnect_protocol', name: 'Interconnect protocol', value: 'OpenMPI' },
      { key: 'limitations_acknowledged', name: 'Limitations acknowledged', value: true },
    ])
    const everything = JSON.stringify(d)
    expect(everything).not.toContain('_computed')
    expect(everything).not.toContain('_postprocessed')
  })

  test('a TRL definition: label is the band, level is the headline, sub-scores have no scale', () => {
    const trl = extraction({
      id: 'e-trl',
      paper: 'p-t',
      extraction_definition: 'def-trl',
      category: 'TRL Level',
      exit_metric: '4',
      fields_data: {
        trl_label: 'TRL 4: Technology validated in lab',
        trl_level: 4,
        justification: 'Validated together in an HPC environment.',
        evidence_quote: 'multiple variational runs were executed',
        trl_level_computed: 4,
        evidence_of_movement: 'E'.repeat(100),
        prototype_maturity_score: 4,
        operational_readiness_score: 3,
      },
    })
    const d = toScoredPaper(paper({ id: 'p-t' }), [trl], contexts).dimensions.find((x) => x.is_trl)!
    expect(d).toMatchObject({ value: 4, max: 9, band: 'Technology validated in lab' })
    expect(d.rationale).toBe('Validated together in an HPC environment.')
    expect(d.evidence).toEqual(['multiple variational runs were executed'])
    expect(d.facets).toEqual([
      {
        key: 'prototype_maturity_score',
        name: 'Prototype maturity',
        value: 4,
        max: null,
        text: null,
      },
      {
        key: 'operational_readiness_score',
        name: 'Operational readiness',
        value: 3,
        max: null,
        text: null,
      },
    ])
    expect(d.texts?.map((x) => x.key)).toEqual(['evidence_of_movement'])
    expect(d.facts).toBeUndefined()
  })

  test('the row’s exit_metric names the headline, so a band string first in the payload is not it', () => {
    const nov = extraction({
      id: 'e-nov',
      paper: 'p-n',
      extraction_definition: 'def-nov',
      category: 'Novelty Score',
      exit_metric: '63.6',
      fields_data: {
        novelty_band: 'Additive',
        justification: 'Combines standard techniques well.',
        novelty_score: 63.6,
        novelty_computed: 63.6,
        key_contributions: ['A self-consistent DFT–VQE loop.'],
        evidence_gaps: ['Noiseless emulation only.'],
        empirical_novelty_score: 68,
      },
    })
    const d = toScoredPaper(paper({ id: 'p-n' }), [nov], contexts).dimensions[1]!
    expect(d).toMatchObject({ key: 'novelty_score', value: 63.6, raw: '63.6', band: 'Additive' })
    expect(d.facets).toEqual([
      { key: 'empirical_novelty_score', name: 'Empirical novelty', value: 68, max: 10, text: null },
    ])
    // "evidence_gaps" is a list of what is missing, not the quoted evidence.
    expect(d.evidence).toBeUndefined()
    expect(d.lists?.map((l) => l.name)).toEqual(['Key contributions', 'Evidence gaps'])
  })

  test('the list composition leaves the detail out', () => {
    const nov = extraction({
      id: 'e-nov3',
      paper: 'p-l',
      extraction_definition: 'def-nov',
      category: 'Novelty Score',
      exit_metric: '7',
      version_info: { llm_model: 'google/gemini-3.8-flash' },
      fields_data: {
        novelty_score: 7,
        novelty_band: 'Fresh',
        reasoning: 'r',
        key_contributions: ['x'],
      },
    })
    const d = toScoredPaper(paper({ id: 'p-l' }), [nov], contexts, { detail: false }).dimensions[1]!
    expect(d).toMatchObject({ value: 7, rationale: 'r' })
    expect(d.band).toBeUndefined()
    expect(d.lists).toBeUndefined()
    expect(d.model).toBeUndefined()
  })

  test('without exit_metric the name-derived resolution stands, detail still shaped', () => {
    const nov = extraction({
      id: 'e-nov2',
      paper: 'p-n2',
      extraction_definition: 'def-nov',
      category: 'Novelty Score',
      fields_data: { novelty_score: 7, reasoning: 'Fresh angle.', key_contributions: ['x'] },
    })
    const d = toScoredPaper(paper({ id: 'p-n2' }), [nov], contexts).dimensions[1]!
    expect(d).toMatchObject({ value: 7, rationale: 'Fresh angle.' })
    expect(d.lists).toEqual([{ key: 'key_contributions', name: 'Key contributions', items: ['x'] }])
    expect(d.facets).toBeUndefined()
  })

  test('the paper carries the two screening stages, the publication date and the run name', () => {
    const p = toScoredPaper(
      paper({
        id: 'p-s',
        abstract_screening_reasoning: 'On topic.',
        full_text_screening_reasoning: 'Full method.',
        published_date: '2026-08-13',
        pipeline_run_name: 'Scheduled Run - Hybrid Computing 2AM',
      }),
      [],
      contexts,
    )
    expect(p).toMatchObject({
      abstract_screening_reasoning: 'On topic.',
      full_text_screening_reasoning: 'Full method.',
      published_date: '2026-08-13',
      pipeline_run_name: 'Scheduled Run - Hybrid Computing 2AM',
    })
    const bare = toScoredPaper(paper({ id: 'p-b' }), [], contexts)
    expect(bare).toMatchObject({
      abstract_screening_reasoning: null,
      full_text_screening_reasoning: null,
      published_date: null,
      pipeline_run_name: null,
    })
  })
})

import { describe, expect, test } from 'bun:test'
import {
  edition,
  editionExclusion,
  editionPage,
  editionPaper,
  editionQuery,
  editionsQuery,
  editionSummary,
} from './schema'

const sampleScoredPaper = {
  id: '00000000-0000-4000-8000-000000000001',
  workspace_id: '00000000-0000-4000-8000-000000000010',
  pipeline_run_id: '00000000-0000-4000-8000-000000000020',
  title: 'Attention Is All You Need',
  authors: ['Ashish Vaswani', 'Noam Shazeer', 'Niki Parmar'],
  authors_raw: 'Ashish Vaswani, Noam Shazeer, Niki Parmar',
  abstract:
    'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.',
  doi: '10.5555/3295222.3295349',
  arxiv_id: '1706.03762',
  source: 'arxiv',
  screening_status: 'accepted' as const,
  screening_reasoning: 'Fundamental architectural breakthrough in transformer models.',
  abstract_screening_reasoning: null,
  full_text_screening_reasoning: null,
  signal_score: 95.5,
  signal_score_details: {
    variables: { novelty: 10, methodology: 9 },
    code_snippet: 'signal = novelty * 0.6 + methodology * 0.4',
    calculated_at: '2026-09-09T10:00:00Z',
    error: null,
  },
  dimensions: [
    {
      key: 'novelty',
      definition_id: '00000000-0000-4000-8000-000000000030',
      name: 'Novelty & Ingenuity',
      value: 9.5,
      raw: '9.5 / 10',
      max: 10,
      is_trl: false,
    },
  ],
  pdf_key: 'papers/1706.03762.pdf',
  markdown_key: 'papers/1706.03762.md',
  source_url: 'https://arxiv.org/abs/1706.03762',
  is_benchmark: false,
  evaluation_label: null,
  published_date: '2017-06-12',
  created_at: '2026-09-09T08:00:00Z',
  pipeline_run_name: 'AI Breakthroughs Scan',
  risk_and_affiliation: {
    affiliations: ['Google Brain', 'Google Research'],
    author_contacts: ['vaswani@google.com'],
    funding_entities: ['Google LLC'],
    codebase_artifact_link: 'https://github.com/tensorflow/tensor2tensor',
    flags: [],
  },
}

describe('Briefings BFF Schema Contracts', () => {
  test('editionPaper validates complete canonical ScoredPaper without coercion', () => {
    const parsed = editionPaper.parse(sampleScoredPaper)
    expect(parsed.id).toBe(sampleScoredPaper.id)
    expect(parsed.signal_score).toBe(95.5)
    expect(parsed.dimensions).toHaveLength(1)
    expect(parsed.dimensions?.[0]?.name).toBe('Novelty & Ingenuity')
    expect(parsed.source_url).toBe('https://arxiv.org/abs/1706.03762')
    expect(parsed.risk_and_affiliation?.affiliations).toContain('Google Brain')
  })

  test('editionExclusion validates screening reasons and paper id', () => {
    const exclusion = {
      paper_id: '00000000-0000-4000-8000-000000000002',
      title: 'Irrelevant Study on Agriculture',
      source: 'arXiv',
      reason: 'Outside domain scope (no AI relevance).',
    }
    const parsed = editionExclusion.parse(exclusion)
    expect(parsed.paper_id).toBe(exclusion.paper_id)
    expect(parsed.reason).toBe(exclusion.reason)

    // Reason can be null
    const parsedNullReason = editionExclusion.parse({ ...exclusion, reason: null })
    expect(parsedNullReason.reason).toBeNull()
  })

  test('editionSummary validates full edition payload with papers array', () => {
    const payload = {
      run_id: '00000000-0000-4000-8000-000000000020',
      workspace_id: '00000000-0000-4000-8000-000000000010',
      date: '2026-09-09',
      title: 'AI Breakthroughs Scan — 2026-09-09',
      in_brief: 'The AI Breakthroughs Scan fetched 15 papers and surfaced 1.',
      in_brief_source: 'template' as const,
      funnel: {
        fetched: 15,
        passed_screening: 3,
        surfaced: 1,
      },
      papers: [sampleScoredPaper],
      generated_at: '2026-09-09T09:30:00+00:00',
    }

    const parsed = editionSummary.parse(payload)
    expect(parsed.date).toBe('2026-09-09')
    expect(parsed.funnel.surfaced).toBe(1)
    expect(parsed.papers[0].title).toBe('Attention Is All You Need')
  })

  test('editionSummary validates backend editions list payload with lightweight paper objects', () => {
    const lightweightPayload = {
      run_id: '00000000-0000-4000-8000-000000000020',
      workspace_id: '00000000-0000-4000-8000-000000000010',
      date: '2026-09-09',
      title: 'AI Breakthroughs Scan — 2026-09-09',
      in_brief: 'Briefing text.',
      in_brief_source: 'template' as const,
      funnel: {
        fetched: 15,
        passed_screening: 3,
        surfaced: 1,
      },
      papers: [
        {
          id: '00000000-0000-4000-8000-000000000001',
          title: 'Lightweight Paper',
          authors: ['A. Researcher', 'B. Scientist'],
          source: 'arXiv',
          screening_status: 'accepted',
          signal_score: 87.5,
        },
      ],
      generated_at: '2026-09-09T09:30:00+00:00',
    }

    const parsed = editionSummary.parse(lightweightPayload)
    expect(parsed.papers[0].id).toBe('00000000-0000-4000-8000-000000000001')
    expect(parsed.papers[0].title).toBe('Lightweight Paper')
    expect(parsed.papers[0].dimensions ?? []).toEqual([])
    expect(parsed.papers[0].doi ?? null).toBeNull()
    expect(parsed.papers[0].arxiv_id ?? null).toBeNull()
    expect(parsed.papers[0].signal_score).toBe(87.5)
  })

  test('edition extends editionSummary with exclusions array', () => {
    const fullEdition = {
      run_id: '00000000-0000-4000-8000-000000000020',
      workspace_id: '00000000-0000-4000-8000-000000000010',
      date: '2026-09-09',
      title: 'AI Breakthroughs Scan — 2026-09-09',
      in_brief: 'In brief summary text.',
      in_brief_source: 'model' as const,
      funnel: {
        fetched: 2,
        passed_screening: 1,
        surfaced: 1,
      },
      papers: [sampleScoredPaper],
      exclusions: [
        {
          paper_id: '00000000-0000-4000-8000-000000000099',
          title: 'Rejected Paper',
          source: 'arXiv',
          reason: 'Fails methodological rigour criteria.',
        },
      ],
      generated_at: null,
    }

    const parsed = edition.parse(fullEdition)
    expect(parsed.exclusions).toHaveLength(1)
    expect(parsed.exclusions[0].title).toBe('Rejected Paper')
  })

  test('edition rejects malformed date format', () => {
    const invalidDatePayload = {
      run_id: '00000000-0000-4000-8000-000000000020',
      workspace_id: '00000000-0000-4000-8000-000000000010',
      date: '09-09-2026', // invalid ISO date
      title: 'Invalid Date Briefing',
      in_brief: 'Text',
      in_brief_source: 'template',
      funnel: { fetched: 0, passed_screening: 0, surfaced: 0 },
      papers: [],
      generated_at: null,
    }
    expect(() => editionSummary.parse(invalidDatePayload)).toThrow()
  })

  test('edition rejects invalid screening_status on paper', () => {
    const paperWithBadStatus = {
      ...sampleScoredPaper,
      screening_status: 'invalid_status_not_in_enum',
    }
    expect(() => editionPaper.parse(paperWithBadStatus)).toThrow()
  })

  test('editionPage wraps editionSummary into paginated envelope', () => {
    const page = {
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          run_id: '00000000-0000-4000-8000-000000000020',
          workspace_id: '00000000-0000-4000-8000-000000000010',
          date: '2026-09-09',
          title: 'Briefing 1',
          in_brief: 'Brief 1',
          in_brief_source: 'template' as const,
          funnel: { fetched: 5, passed_screening: 2, surfaced: 1 },
          papers: [sampleScoredPaper],
          generated_at: null,
        },
      ],
    }
    const parsed = editionPage.parse(page)
    expect(parsed.count).toBe(1)
    expect(parsed.results).toHaveLength(1)
  })

  test('editionQuery and editionsQuery validate optional uuid parameters', () => {
    const q1 = editionQuery.parse({
      workspace_id: '00000000-0000-4000-8000-000000000010',
      run_id: '00000000-0000-4000-8000-000000000020',
    })
    expect(q1.workspace_id).toBe('00000000-0000-4000-8000-000000000010')

    const q2 = editionsQuery.parse({ page: 2, page_size: 10 })
    expect(q2.page).toBe(2)
    expect(q2.page_size).toBe(10)
    expect(q2.workspace_id).toBeUndefined()
  })
})

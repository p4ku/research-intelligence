/**
 * Contract-shaped workspace fixtures for the Studio overview: the paper
 * fixture's workspace plus the states the overview must design for — a
 * workspace with no runs and no definitions, one close to its USD budget,
 * and one with a German-length name. Deterministic fake UUIDs; validated by
 * src/lib/bff/fixtures.test.ts. Pure.
 */
import { fixtureWorkspace } from '../papers/fixtures'
import type { WorkspaceSummary } from './schema'

export const fixtureEmptyWorkspace: WorkspaceSummary = {
  id: '00000000-0000-4000-8000-000000000002',
  name: 'hybrid-computing-callibration',
  user_role: 'admin',
  definitions: [],
  scrapers: [
    {
      id: '00000000-0000-4000-8000-000000000022',
      provider: 'arxiv',
      search_query: 'all:"hybrid computing"',
      is_active: false,
    },
  ],
  digest_schedule: null,
  screening_llm_model: 'google/gemini-3.7-flash',
  llm_provider: 'google',
  created_at: '2026-08-30T07:52:00Z',
  monthly_usd_limit: 50,
  usd_spent: 0,
  monthly_token_limit: 10_000_000,
  tokens_consumed: 0,
}

export const fixtureBudgetWorkspace: WorkspaceSummary = {
  id: '00000000-0000-4000-8000-000000000003',
  name: 'Quantum Sensing & Metrology for Industrial Inspection',
  user_role: 'manager',
  definitions: [
    {
      id: '00000000-0000-4000-8000-000000000014',
      name: 'TRL Level',
      key: 'trl_level',
      is_active: true,
      is_trl: true,
      max: 9,
    },
    {
      id: '00000000-0000-4000-8000-000000000015',
      name: 'Schwarz Fit',
      key: 'schwarz_fit',
      is_active: true,
      is_trl: false,
      max: 100,
    },
  ],
  scrapers: [
    {
      id: '00000000-0000-4000-8000-000000000023',
      provider: 'arxiv',
      search_query: 'ti:"quantum sensing" OR ti:"NV center"',
      is_active: true,
    },
  ],
  digest_schedule: null,
  screening_llm_model: 'anthropic/claude-sonnet-4-5',
  llm_provider: 'anthropic',
  created_at: '2026-08-31T09:20:00Z',
  monthly_usd_limit: 25,
  usd_spent: 21.4,
  monthly_token_limit: 8_000_000,
  tokens_consumed: 2_601_300,
}

export const fixtureWorkspaces: WorkspaceSummary[] = [
  fixtureWorkspace,
  fixtureEmptyWorkspace,
  fixtureBudgetWorkspace,
]

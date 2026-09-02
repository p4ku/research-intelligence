import type { WorkspaceDTO } from '@/lib/api/types'
import { toWorkspaceSummary } from '@/lib/papers/map'
import { describe, expect, test } from 'bun:test'
import { workspace } from './schema'
import { workspaceDTO } from './upstream'

// Production sends `digest_schedule: null` for every workspace: the model
// field was removed (19df1ac) and the serializer keeps the key as a
// compatibility shim that always returns null (f3942c4). The DTO required a
// string, so `/api/workspaces/` failed upstream-shape and every page rendered
// "Couldn't reach the backend" while the API was healthy (2026-09-02).
const fromProduction = {
  id: '3f1c2a6e-4b7d-4e0a-9c1d-2a5b6c7d8e9f',
  name: 'Battery materials',
  scrapers: [],
  abstract_acceptance_criteria: '',
  abstract_rejection_criteria: '',
  full_text_acceptance_criteria: '',
  full_text_rejection_criteria: '',
  extraction_definitions: [],
  ocr_provider: null,
  screening_llm_model: 'claude-sonnet-5',
  llm_provider: 'anthropic',
  digest_schedule: null,
  monthly_token_limit: 1_000_000,
  tokens_in_consumed_this_month: 0,
  tokens_out_consumed_this_month: 0,
  tokens_consumed_this_month: 0,
  monthly_usd_limit: '100.00',
  usd_spent_this_month: '0.00',
  subscribers: [],
  user_role: 'admin',
  created_at: '2026-09-01T22:18:20Z',
}

describe('workspace upstream DTO', () => {
  test('accepts a null digest_schedule', () => {
    const parsed = workspaceDTO.safeParse(fromProduction)
    expect(parsed.success).toBe(true)
  })

  test('still accepts a cron string', () => {
    const parsed = workspaceDTO.safeParse({ ...fromProduction, digest_schedule: '0 7 * * *' })
    expect(parsed.success).toBe(true)
  })

  test('maps to a contract-valid summary with digest_schedule null', () => {
    const dto = workspaceDTO.parse(fromProduction) as WorkspaceDTO
    const summary = toWorkspaceSummary(dto, new Map())
    expect(summary.digest_schedule).toBeNull()
    expect(workspace.safeParse(summary).success).toBe(true)
  })
})

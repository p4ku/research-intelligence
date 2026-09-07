/**
 * Aggregates every resource's `contract.ts` (pure). Consumed by
 * `/bff/status`, `scripts/contract-spec.ts`, and `scripts/contract-check.ts`.
 * Resources register here as their slices land.
 */
import { briefingsOperations } from './briefings/contract'
import { chatOperations } from './chat/contract'
import { componentRunsOperations } from './component-runs/contract'
import type { Operation } from './core/contract-types'
import { papersOperations } from './papers/contract'
import { pipelineRunsOperations } from './pipeline-runs/contract'
import { scoringOperations } from './scoring/contract'
import { searchOperations } from './search/contract'
import { settingsOperations } from './settings/contract'
import { starsOperations } from './stars/contract'
import { workspacesOperations } from './workspaces/contract'

export const allOperations: Operation[] = [
  ...papersOperations,
  ...chatOperations,
  ...briefingsOperations,
  ...settingsOperations,
  ...scoringOperations,
  ...starsOperations,
  ...searchOperations,
  ...workspacesOperations,
  ...pipelineRunsOperations,
  ...componentRunsOperations,
]

export const djangoOperations = (kind: 'current' | 'desired') =>
  allOperations.filter((op) => op.face === 'django' && op.kind === kind)

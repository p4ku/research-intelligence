// The frontend's paper model — re-exported from the BFF contract schemas
// (src/lib/bff/papers/schema.ts, src/lib/bff/workspaces/schema.ts), which are
// the single source of truth: zod validates Django against exactly these
// shapes, and the OpenAPI handed to the backend team is generated from them.
// Pages and components import from here and never see DTOs.

export {
  PASSED_STATUSES,
  SCREENING_STATUSES,
  type Dimension,
  type DimensionFacet,
  type DimensionField,
  type DimensionList,
  type NarrativeReportSummary,
  type RiskAndAffiliation,
  type RiskFlag,
  type ScoredPaper,
  type ScreeningStatus,
  type SignalScoreDetails,
} from '@/lib/bff/papers/schema'
export type { DefinitionSummary, WorkspaceSummary } from '@/lib/bff/workspaces/schema'

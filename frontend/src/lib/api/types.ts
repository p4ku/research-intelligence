// Response shapes of the Django REST API *as it exists today*, inferred from
// the zod transcriptions in src/lib/bff/<resource>/upstream.ts so the static
// types can never drift from what the BFF validates at runtime. Notes:
//
// - Every current list endpoint returns a bare array — no pagination, no
//   envelope — spanning every workspace the user belongs to.
// - UUIDs and foreign keys are strings; DRF Decimals are strings.
// - `PaperDTO` has no signal_score; it lives on the nested `metrics[]`.
// - `ExtractionDTO` carries `fields_data` but not the model's `exit_metric`
//   property, so dimension values are derived in src/lib/papers/map.ts.

import type { componentRunDTO } from '@/lib/bff/component-runs/upstream'
import type {
  extractionDTO,
  paperDTO,
  paperMetricDTO,
  signalScoreDetailsDTO,
} from '@/lib/bff/papers/upstream'
import type { pipelineRunDTO, pipelineRunDetailDTO } from '@/lib/bff/pipeline-runs/upstream'
import type {
  extractionDefinitionDTO,
  scraperDTO,
  subscriberDTO,
  workspaceDTO,
} from '@/lib/bff/workspaces/upstream'
import type * as z from 'zod'

export type SignalScoreDetailsDTO = z.infer<typeof signalScoreDetailsDTO>
export type PaperMetricDTO = z.infer<typeof paperMetricDTO>
export type PaperDTO = z.infer<typeof paperDTO>
export type ExtractionDTO = z.infer<typeof extractionDTO>
export type ExtractionDefinitionDTO = z.infer<typeof extractionDefinitionDTO>
export type ScraperDTO = z.infer<typeof scraperDTO>
export type SubscriberDTO = z.infer<typeof subscriberDTO>
export type WorkspaceDTO = z.infer<typeof workspaceDTO>
export type PipelineRunDTO = z.infer<typeof pipelineRunDTO>
export type PipelineRunDetailDTO = z.infer<typeof pipelineRunDetailDTO>
export type ComponentRunDTO = z.infer<typeof componentRunDTO>

export type ScreeningStatusDTO = string

/** Nested field form written by the extraction engine. */
export interface FieldExtractionDTO {
  value: unknown
  normalized_value?: string | null
  confidence?: number
  evidence?: { quote?: string; rationale?: string }[]
}

export type FieldValueDTO =
  | number
  | string
  | boolean
  | null
  | string[]
  | FieldExtractionDTO
  | Record<string, unknown>

/** Either a flat map of fields or `{ fields: { … } }`. */
export type FieldsDataDTO = Record<string, FieldValueDTO | unknown>

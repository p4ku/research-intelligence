/**
 * The contract registry's building block. Every resource declares its
 * operations in a pure `contract.ts`; the aggregator (`src/lib/bff/contract.ts`)
 * feeds them to `/bff/status`, `scripts/contract-spec.ts` (OpenAPI), and
 * `scripts/contract-check.ts` (conformance). Pure.
 */
import type * as z from 'zod'
import type { ResourceName } from './source'

/** Path params the conformance/probe context can fill. */
export type ProbeParam = 'workspace_id' | 'paper_id' | 'run_id' | 'session_id' | 'date'

export interface Operation {
  /** Unique, stable id, e.g. `papers.list.desired`. */
  id: string
  resource: ResourceName | 'auth'
  /** `django` ops describe Django endpoints; `bff` ops describe our own routes. */
  face: 'django' | 'bff'
  /**
   * For `django` ops: `current` = an endpoint the BFF depends on today
   * (a failure breaks the app now); `desired` = an endpoint we are asking
   * the backend team to build (missing until then).
   */
  kind: 'current' | 'desired' | 'bff'
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** Path template with `{param}` placeholders, e.g. `/api/workspaces/{workspace_id}/papers/`. */
  path: string
  summary: string
  query?: z.ZodType
  body?: z.ZodType
  /** Success responses by status; 4xx/5xx are always problem+json. */
  responses: Record<number, z.ZodType>
  /** Which path params the checker must fill; unfillable ops are skipped. */
  probe?: { requires: readonly ProbeParam[] }
  /**
   * For a `desired` op that upgrades an existing endpoint in place: the id of
   * the `current` op it replaces. A response that still matches the current
   * shape is reported as not-yet-built rather than as a mismatch.
   */
  supersedes?: string
  /** Server-Sent Events endpoint: the checker never executes it. */
  sse?: boolean
}

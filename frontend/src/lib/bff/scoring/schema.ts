/**
 * OUR scoring contract: how a workspace's signal score is computed — the
 * Python snippet (read-only; the formula stays backend-owned and users never
 * edit it), the variables it sees, per-dimension weights, and a worked
 * example. Pure.
 */
import * as z from 'zod'

export const scoringVariable = z
  .object({
    key: z.string(),
    definition_id: z.uuid().nullable(),
    name: z.string(),
    max: z.number().nullable(),
    is_trl: z.boolean(),
  })
  .meta({ id: 'ScoringVariable' })
export type ScoringVariable = z.infer<typeof scoringVariable>

export const scoringWeight = z
  .object({
    key: z.string(),
    definition_id: z.uuid().nullable(),
    name: z.string(),
    /** Relative weight; the UI normalises to 100. */
    weight: z.number(),
  })
  .meta({ id: 'ScoringWeight' })
export type ScoringWeight = z.infer<typeof scoringWeight>

export const workspaceScoring = z
  .object({
    workspace_id: z.uuid(),
    /** The workspace's signal_score_code Python snippet. */
    code: z.string().nullable(),
    /** 'workspace' once served from the workspace itself; 'latest_metric'
     *  while read off the newest scored paper's evaluation record. */
    code_source: z.enum(['workspace', 'latest_metric', 'stub']),
    variables: z.array(scoringVariable),
    weights: z.array(scoringWeight),
    /** 'stub' = an even placeholder split until the backend exposes weights. */
    weights_source: z.enum(['backend', 'stub']),
    example: z
      .object({
        paper_id: z.uuid(),
        title: z.string(),
        signal_score: z.number().nullable(),
        variables: z.record(z.string(), z.union([z.number(), z.string()])),
      })
      .nullable(),
  })
  .meta({ id: 'WorkspaceScoring' })
export type WorkspaceScoring = z.infer<typeof workspaceScoring>

export const scoringQuery = z.object({ workspace_id: z.uuid() })

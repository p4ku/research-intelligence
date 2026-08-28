/**
 * OUR pipeline-run contract: the slice of a run the UI needs (funnel counters,
 * dates, status line). Django's current serializer is richer; the requested
 * endpoint may simply paginate the existing shape — the BFF trims it. Pure.
 */
import * as z from 'zod'
import { listQuery, pageSchema } from '../core/pagination'

export const runStatus = z
  .enum(['pending', 'running', 'completed', 'failed', 'aborted'])
  .meta({ id: 'PipelineRunStatus' })
export type RunStatus = z.infer<typeof runStatus>

export const pipelineRun = z
  .object({
    id: z.uuid(),
    workspace_id: z.uuid(),
    /** The trigger date (YYYY-MM-DD). */
    run_date: z.iso.date(),
    status: runStatus,
    current_stage: z.string().nullable(),
    total_papers_fetched: z.number().int(),
    total_papers_passed_screening: z.number().int(),
    /** The engine's one-line human summary of the run. */
    status_message: z.string().nullable(),
    started_at: z.iso.datetime({ offset: true }).nullable(),
    completed_at: z.iso.datetime({ offset: true }).nullable(),
  })
  .meta({ id: 'PipelineRun' })
export type PipelineRun = z.infer<typeof pipelineRun>

export const runsQuery = listQuery.extend({
  workspace_id: z.uuid(),
  status: runStatus.optional(),
})
export type RunsQuery = z.infer<typeof runsQuery>

export const runPage = pageSchema(pipelineRun).meta({ id: 'PipelineRunPage' })

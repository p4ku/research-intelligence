/**
 * The RFC 9457 problem shape as a zod schema — registered so the generated
 * OpenAPI can reference `#/components/schemas/Problem`. Pure. (Kept separate
 * from problem.ts so the proxy bundle stays zod-free.)
 */
import * as z from 'zod'

export const problemSchema = z
  .object({
    type: z.string().describe('Stable relative problem type, e.g. /problems/validation'),
    title: z.string(),
    status: z.number().int(),
    detail: z.string().optional(),
    instance: z.string().optional(),
    errors: z.record(z.string(), z.array(z.string())).optional().describe('DRF-style field errors'),
    source: z.string().optional().describe('BFF source that produced the response'),
  })
  .meta({ id: 'Problem' })

import { bff } from '@/lib/bff/core/handler'
import { runs } from '@/lib/bff/pipeline-runs/service'

export const dynamic = 'force-dynamic'

/** The Studio overview's payload: every visible run plus every workspace. */
export const GET = bff('pipeline-runs', async () => Response.json(await runs.overview()))

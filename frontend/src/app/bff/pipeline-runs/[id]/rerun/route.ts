import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { invalidateCorpusSnapshot } from '@/lib/bff/corpus/snapshot'
import { runs } from '@/lib/bff/pipeline-runs/service'
import { workspaces } from '@/lib/bff/workspaces/service'

export const dynamic = 'force-dynamic'

/**
 * Rerun one run from a step or from the failed stage. Refusal shapes are the
 * service's (403 unless the caller is an admin of the domain).
 */
export const POST = bff('pipeline-runs', async (request, ctx) => {
  const { id } = await ctx.params
  const targetRun = await runs.get(id)
  if (targetRun) {
    const targetWs = await workspaces.get(targetRun.workspace_id)
    if (targetWs && targetWs.user_role !== 'admin') {
      throw problem('forbidden', {
        detail: `Role '${targetWs.user_role ?? 'unknown'}' cannot rerun runs. Admin role is required.`,
      })
    }
  }

  let stepName: string | undefined
  try {
    const body = await request.json()
    if (body && typeof body.step_name === 'string') {
      stepName = body.step_name
    }
  } catch {
    // Body is optional
  }
  const restarted = await runs.rerun(id, stepName)
  invalidateCorpusSnapshot()
  return Response.json(restarted)
})

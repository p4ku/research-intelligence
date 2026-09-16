import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { parseBody } from '@/lib/bff/core/validate'
import { invalidateCorpusSnapshot } from '@/lib/bff/corpus/snapshot'
import { admission, refusalDetail } from '@/lib/bff/pipeline-runs/admission'
import { startRun } from '@/lib/bff/pipeline-runs/schema'
import { runs } from '@/lib/bff/pipeline-runs/service'
import { workspaces } from '@/lib/bff/workspaces/service'

export const dynamic = 'force-dynamic'

/**
 * Home's "Start" (New briefing) and a failed row's Retry: one domain, one search
 * window. Refuses with 403 unless the caller is an admin or manager of the domain.
 * Django admits at most five runs in flight per domain and refuses
 * a window that is already running (409, `run_limit_reached` /
 * `duplicate_run`) — that is the rule. The same verdict is taken here first
 * from the live list, so a stale Home (another analyst filled the domain, or
 * started this window, since it rendered) gets its 409 without a Django
 * round-trip and re-reads itself; a start that slips past this check in the
 * window before Django's row lock gets the same 409 from Django.
 */
export const POST = bff('pipeline-runs', async (request) => {
  const input = await parseBody(startRun, request)
  const targetWs = await workspaces.get(input.workspace_id)
  if (targetWs && targetWs.user_role !== 'admin' && targetWs.user_role !== 'manager') {
    throw problem('forbidden', {
      detail: `Role '${targetWs.user_role ?? 'unknown'}' cannot start runs. Manager or Admin role is required.`,
    })
  }
  const verdict = admission(await runs.listEverywhere(), input)
  if (!verdict.ok) throw problem('conflict', { detail: refusalDetail(verdict) })
  const started = await runs.start(input)
  invalidateCorpusSnapshot()
  return Response.json(started, { status: 201 })
})

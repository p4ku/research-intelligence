/**
 * The engineering status of the BFF seam: which source feeds each resource
 * and whether the *requested* Django endpoints exist yet. Server-only.
 */
import 'server-only'

import { apiFetch } from '@/lib/api/server'
import { papers } from '../papers/service'
import { runs } from '../pipeline-runs/service'
import { workspaces } from '../workspaces/service'
import { djangoOperations } from '../contract'
import type { Operation, ProbeParam } from '../core/contract-types'
import { RESOURCES, sourceOf, type ResourceName } from '../core/source'

export type ProbeState = 'present' | 'missing' | 'unauthenticated' | 'unreachable' | 'skipped'

export interface DesiredEndpointStatus {
  method: string
  path: string
  state: ProbeState
}

export interface ResourceStatus {
  name: ResourceName
  source: string
  default: string
  supports: readonly string[]
  env: string
  desired: DesiredEndpointStatus[]
}

export interface BffStatus {
  generated_at: string
  build_id: string | null
  resources: ResourceStatus[]
}

async function probeContext(): Promise<Partial<Record<ProbeParam, string>>> {
  const ctx: Partial<Record<ProbeParam, string>> = {}
  try {
    const all = await workspaces.listAllSafe()
    if (all[0]) {
      ctx.workspace_id = all[0].id
      const [wsPapers, wsRuns] = await Promise.all([
        papers.listAll(all[0].id).catch(() => null),
        runs.listAll(all[0].id).catch(() => []),
      ])
      if (wsPapers?.papers[0]) ctx.paper_id = wsPapers.papers[0].id
      if (wsRuns[0]) ctx.run_id = wsRuns[0].id
    }
  } catch {
    // No context — probes that need path params are reported as skipped.
  }
  return ctx
}

function fillPath(op: Operation, ctx: Partial<Record<ProbeParam, string>>): string | null {
  let path = op.path
  for (const param of op.probe?.requires ?? []) {
    const value = ctx[param]
    if (!value) return null
    path = path.replace(`{${param}}`, value)
  }
  return path.includes('{') ? null : path
}

/**
 * OPTIONS is side-effect-free and cheap: DRF answers 200 on any routed view
 * (POST-only ones included), 404 when the route does not exist, 401 without
 * a token.
 */
async function probe(path: string): Promise<ProbeState> {
  try {
    const res = await apiFetch(path, { method: 'OPTIONS' })
    if (res.ok) return 'present'
    if (res.status === 401) return 'unauthenticated'
    return 'missing'
  } catch {
    return 'unreachable'
  }
}

export async function bffStatus(): Promise<BffStatus> {
  const desired = djangoOperations('desired')
  const ctx = desired.length > 0 ? await probeContext() : {}
  const byResource = new Map<string, DesiredEndpointStatus[]>()

  await Promise.all(
    desired.map(async (op) => {
      const path = fillPath(op, ctx)
      const state = path ? await probe(path) : 'skipped'
      const list = byResource.get(op.resource) ?? []
      list.push({ method: op.method, path: op.path, state })
      byResource.set(op.resource, list)
    }),
  )

  return {
    generated_at: new Date().toISOString(),
    build_id: process.env.BUILD_ID ?? null,
    resources: Object.values(RESOURCES).map((def) => ({
      name: def.name,
      source: sourceOf(def.name),
      default: def.defaultSource,
      supports: def.supports,
      env: def.env,
      desired: byResource.get(def.name) ?? [],
    })),
  }
}

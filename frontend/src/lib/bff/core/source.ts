/**
 * The BFF resource registry: which data sources each resource supports and
 * which one is active. Pure — importable from the proxy, route handlers,
 * services, and the contract scripts alike.
 *
 * - `stub`     — checked-in fixtures in the contract shape (no backend needed).
 * - `composed` — assembled in the BFF from the Django endpoints that exist today.
 * - `django`   — the contract endpoint on Django, as a validated pass-through.
 *
 * Flip with `BFF_SOURCE_<RESOURCE>=stub|composed|django`. Flipping a resource
 * to `django` is the backend team's "done" signal for that contract; the
 * defaults here describe what works against today's backend.
 */

export const SOURCES = ['stub', 'composed', 'django'] as const
export type Source = (typeof SOURCES)[number]

export type ResourceName =
  | 'papers'
  | 'workspaces'
  | 'pipeline-runs'
  | 'component-runs'
  | 'chat'
  | 'briefings'
  | 'preferences'
  | 'scoring'
  | 'stars'

export interface ResourceDef {
  name: ResourceName
  /** Environment variable that overrides the source for this resource. */
  env: string
  /** Modes the service actually implements. */
  supports: readonly Source[]
  /** Best mode that works against today's backend. */
  defaultSource: Source
}

function def(
  name: ResourceName,
  env: string,
  supports: readonly Source[],
  defaultSource: Source,
): ResourceDef {
  return { name, env, supports, defaultSource }
}

export const RESOURCES: Record<ResourceName, ResourceDef> = {
  papers: def('papers', 'BFF_SOURCE_PAPERS', ['stub', 'composed', 'django'], 'composed'),
  workspaces: def('workspaces', 'BFF_SOURCE_WORKSPACES', ['django'], 'django'),
  'pipeline-runs': def('pipeline-runs', 'BFF_SOURCE_PIPELINE_RUNS', ['django'], 'django'),
  'component-runs': def('component-runs', 'BFF_SOURCE_COMPONENT_RUNS', ['django'], 'django'),
  chat: def('chat', 'BFF_SOURCE_CHAT', ['stub', 'django'], 'django'),
  briefings: def('briefings', 'BFF_SOURCE_BRIEFINGS', ['stub', 'composed', 'django'], 'composed'),
  preferences: def('preferences', 'BFF_SOURCE_PREFERENCES', ['stub', 'django'], 'stub'),
  scoring: def('scoring', 'BFF_SOURCE_SCORING', ['stub', 'composed', 'django'], 'composed'),
  stars: def('stars', 'BFF_SOURCE_STARS', ['stub', 'django'], 'stub'),
}

const warned = new Set<ResourceName>()

/** The active source for a resource: env override when valid, else the default. */
export function sourceOf(name: ResourceName): Source {
  const resource = RESOURCES[name]
  const raw = process.env[resource.env]?.trim().toLowerCase()
  if (!raw) return resource.defaultSource
  if ((resource.supports as readonly string[]).includes(raw)) return raw as Source
  if (!warned.has(name)) {
    warned.add(name)
    console.warn(
      `[bff] ${resource.env}=${raw} is not one of [${resource.supports.join(', ')}]; using "${resource.defaultSource}"`,
    )
  }
  return resource.defaultSource
}

import { isUuid } from '@/lib/bff/core/validate'
import type { WorkspaceSummary } from '@/lib/papers/types'

/**
 * The `?domain=` of an edition URL, when it names one of the user's domains.
 * Anything else — a link from before domains were in the URL, a typo, a
 * domain the user has since left — resolves to undefined, and the page falls
 * back to the newest edition of that day rather than a 404.
 */
export function domainScope(all: Pick<WorkspaceSummary, 'id'>[], domain: string | undefined) {
  return domain && isUuid(domain) && all.some((ws) => ws.id === domain) ? domain : undefined
}

/** Domain names by workspace id, for crumbs and badges. */
export function domainNames(
  all: readonly Pick<WorkspaceSummary, 'id' | 'name'>[],
): Record<string, string> {
  return Object.fromEntries(all.map((ws) => [ws.id, ws.name]))
}

/**
 * The `?run=` of an edition URL: the run whose edition the page shows, when
 * it is a well-formed id. Whether the run exists is the service's question;
 * an unknown run, like an unknown domain, falls back to the day's newest
 * edition rather than a 404.
 */
export function runScope(run: string | undefined): string | undefined {
  return run && isUuid(run) ? run : undefined
}

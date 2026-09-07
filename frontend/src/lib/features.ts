/**
 * Demo feature flags: per-browser switches in the account menu that hide a
 * feature live and put it back. Pure — no React, no `next/headers` — so the
 * server reader, the client provider, the status service and the tests all
 * import the same registry. Shaped like RESOURCES in src/lib/bff/core/source.ts.
 *
 * The cookie lists what is OFF: an absent, empty or malformed value is the
 * whole product, a flag added later is on for browsers carrying an old value,
 * and unknown tokens are ignored. That inversion stays inside the codec —
 * components only ever see `Features`, where `true` means shown.
 *
 * This is a preference the visitor owns, not an authorization boundary: the
 * BFF keeps serving whatever the flags say (docs/design/feature-flags.md).
 */

export const FEATURES_COOKIE = 'rs-features'

export type FeatureKey = 'all_papers' | 'stars' | 'ask'

export interface FeatureDef {
  key: FeatureKey
  /** English source string; translated through t() at the call site. */
  label: string
  /** Gettext context for the label, so it reuses an existing German value. */
  ctx?: string
  /** The route this flag owns: the 404 gate and the vanish guard. */
  route?: { href: string; exact: boolean }
}

export const FEATURES: Record<FeatureKey, FeatureDef> = {
  // exact: /papers/<id> must survive when the *list* is hidden.
  all_papers: { key: 'all_papers', label: 'All papers', route: { href: '/papers', exact: true } },
  stars: { key: 'stars', label: 'Stars' },
  ask: { key: 'ask', label: 'Ask', ctx: 'nav', route: { href: '/ask', exact: true } },
}

export const FEATURE_KEYS = Object.keys(FEATURES) as FeatureKey[]

export type Features = Record<FeatureKey, boolean>

export const ALL_ON: Features = { all_papers: true, stars: true, ask: true }

/** Separator that survives cookie serialisation unencoded (see bff/stars/cookie.ts). */
const SEP = '.'

/** A missing, empty or malformed cookie is simply "everything on". */
export function decodeFeaturesCookie(raw: string | undefined): Features {
  const off = new Set((raw ?? '').split(SEP).map((s) => s.trim().toLowerCase()))
  return Object.fromEntries(FEATURE_KEYS.map((k) => [k, !off.has(k)])) as Features
}

/** Registry order, so the value never churns between writes; all-on is ''. */
export function encodeFeaturesCookie(features: Features): string {
  return FEATURE_KEYS.filter((k) => !features[k]).join(SEP)
}

/** The one nav-filter rule, unit-testable without rendering the shell. */
export function isVisible<T extends { feature?: FeatureKey }>(
  item: T,
  features: Features,
): boolean {
  return !item.feature || features[item.feature]
}

/** The flag whose route the pathname is on, if any — turning it off must leave the page. */
export function featureOwning(pathname: string): FeatureKey | undefined {
  return FEATURE_KEYS.find((k) => {
    const route = FEATURES[k].route
    if (!route) return false
    return route.exact ? pathname === route.href : pathname.startsWith(route.href)
  })
}

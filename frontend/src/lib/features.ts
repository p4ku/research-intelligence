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
  /**
   * A value the menu cannot change. A fixed flag reads this way in every
   * browser: the cookie is ignored for it, it is never written to the cookie,
   * and it has no toggle row. Set while a surface is kept out of the product
   * (or in it) without tearing out the flag's plumbing; delete the property to
   * hand the switch back to the account menu.
   */
  fixed?: boolean
}

// 9 Sep 2026: every flag is fixed, so the "Demo features" section of the
// account menu is empty and does not render. /papers and /ask are hidden;
// stars stay on.
export const FEATURES: Record<FeatureKey, FeatureDef> = {
  // exact: /papers/<id> must survive when the *list* is hidden.
  all_papers: {
    key: 'all_papers',
    label: 'All papers',
    route: { href: '/papers', exact: true },
    fixed: false,
  },
  stars: { key: 'stars', label: 'Stars', fixed: true },
  ask: { key: 'ask', label: 'Ask', ctx: 'nav', route: { href: '/ask', exact: true }, fixed: false },
}

export type FeatureRegistry = Record<FeatureKey, FeatureDef>

export const FEATURE_KEYS = Object.keys(FEATURES) as FeatureKey[]

/** The flags the account menu can flip: registry order, fixed ones left out. */
export const TOGGLE_KEYS: FeatureKey[] = FEATURE_KEYS.filter((k) => FEATURES[k].fixed === undefined)

export type Features = Record<FeatureKey, boolean>

/** The registry with nothing hidden — a test value, not what any request sees. */
export const ALL_ON: Features = { all_papers: true, stars: true, ask: true }

/** Separator that survives cookie serialisation unencoded (see bff/stars/cookie.ts). */
const SEP = '.'

/**
 * A missing, empty or malformed cookie is simply "everything on" — except for
 * a fixed flag, which reads its fixed value whatever the cookie says. The
 * registry parameter exists for the tests, so the codec stays exercised while
 * every real flag is fixed.
 */
export function decodeFeaturesCookie(
  raw: string | undefined,
  registry: FeatureRegistry = FEATURES,
): Features {
  const off = new Set((raw ?? '').split(SEP).map((s) => s.trim().toLowerCase()))
  return Object.fromEntries(
    FEATURE_KEYS.map((k) => [k, registry[k].fixed ?? !off.has(k)]),
  ) as Features
}

/**
 * What a request with no cookie reads: every fixed flag at its value, every
 * other flag on. The runtime default everywhere a component or provider has
 * no cookie to read — the no-provider context, Studio's pin, prop defaults —
 * so a unit render or the skeleton gallery shows the product as shipped.
 */
export const DEFAULT_FEATURES: Features = decodeFeaturesCookie(undefined)

/**
 * Registry order, so the value never churns between writes; all-on is ''.
 * Fixed flags are never written, so a cookie from today does not carry a
 * stale "off" into the day the switch comes back.
 */
export function encodeFeaturesCookie(
  features: Features,
  registry: FeatureRegistry = FEATURES,
): string {
  return FEATURE_KEYS.filter((k) => registry[k].fixed === undefined && !features[k]).join(SEP)
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

import 'server-only'

import { cookies } from 'next/headers'
import { notFound } from 'next/navigation'
import { cache } from 'react'
import { decodeFeaturesCookie, FEATURES_COOKIE, type FeatureKey, type Features } from './features'

/**
 * The demo flags for this request, deduped per request like
 * getWorkspacesState. All logic lives in the pure module; this only reads
 * the cookie.
 */
export const getFeatures = cache(
  async (): Promise<Features> =>
    decodeFeaturesCookie((await cookies()).get(FEATURES_COOKIE)?.value),
)

export async function hasFeature(key: FeatureKey): Promise<boolean> {
  return (await getFeatures())[key]
}

/** First line of a flagged page: off means the route does not exist. */
export async function requireFeature(key: FeatureKey): Promise<void> {
  if (!(await hasFeature(key))) notFound()
}

import type { FeatureKey } from '@/lib/features'
import { describe, expect, test } from 'bun:test'
import { join } from 'node:path'

/**
 * Flagged-route convention: a page a demo flag can hide must call
 * `requireFeature('<key>')`, so the route stops existing rather than merely
 * losing its nav entry (docs/design/feature-flags.md §3.6).
 *
 * One row per flagged page. Filtering the nav item is easy to keep; the gate
 * on the page itself is what a refactor drops silently, which is why it is
 * asserted from the file text — rendering a server page is not something this
 * repo does in `bun test`.
 */
const FLAGGED: { route: string; feature: FeatureKey; page: string }[] = [
  { route: '/ask', feature: 'ask', page: '(sidebar)/ask/page.tsx' },
]

describe('flagged routes', () => {
  test.each(FLAGGED)('$route gates on $feature', async ({ feature, page }) => {
    const src = await Bun.file(join(import.meta.dir, page)).text()
    expect(src).toContain(`requireFeature('${feature}')`)
  })
})

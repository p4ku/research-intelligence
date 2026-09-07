import { FEATURES, type FeatureKey } from '@/lib/features'
import { describe, expect, test } from 'bun:test'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

/**
 * Flag convention: a page a demo flag owns opts in explicitly, so the gate
 * cannot be lost in a refactor. Rendering a server page under `bun test` is not
 * something this repo does (and `requireFeature` would need a `next/headers`
 * mock), so this reads the source the way loading-convention.test.ts does.
 *
 * Add a route here in the same PR that gates it. `ask/page.tsx` lands with the
 * `ask` flag.
 */
const GATED: Record<string, FeatureKey> = {
  '(sidebar)/papers/page.tsx': 'all_papers',
}

describe('flagged routes', () => {
  test('every gated page calls requireFeature with its own flag', async () => {
    for (const [rel, key] of Object.entries(GATED)) {
      const abs = join(import.meta.dir, rel)
      expect(existsSync(abs)).toBe(true)
      const src = await Bun.file(abs).text()
      expect(src).toContain(`requireFeature('${key}')`)
    }
  })

  test('every gated page also gates its generateMetadata', async () => {
    for (const [rel, key] of Object.entries(GATED)) {
      const src = await Bun.file(join(import.meta.dir, rel)).text()
      // A page without metadata needs no gate; one with it must not title the
      // 404's tab after the feature it is hiding.
      if (!src.includes('generateMetadata')) continue
      expect(src).toContain(`hasFeature('${key}')`)
    }
  })

  test('each gated route matches the flag that owns it in the registry', () => {
    for (const [rel, key] of Object.entries(GATED)) {
      const route = FEATURES[key].route
      expect(route).toBeDefined()
      // '(sidebar)/papers/page.tsx' -> '/papers'
      const href = '/' + rel.replace(/^\(.*?\)\//, '').replace(/\/page\.tsx$/, '')
      expect(route!.href).toBe(href)
    }
  })
})

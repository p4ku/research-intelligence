import { describe, expect, test } from 'bun:test'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'

/**
 * Streaming convention: every force-dynamic page ships a sibling loading.tsx
 * shell so navigation never freezes on the previous page.
 *
 * KNOWN_UNCOVERED is the debt list — it may only shrink. Cover a page (give it
 * a loading.tsx composed from its section skeletons) and remove it here; a new
 * dynamic page must ship its skeleton from the start.
 */
const KNOWN_UNCOVERED = new Set([
  'page.tsx', // login — redirects straight to /dashboard when a session exists
  '(sidebar)/papers/page.tsx', // the `--stream /papers` negative control in docs/skeletons.md
  '(sidebar)/settings/page.tsx',
  '(sidebar)/tuning/page.tsx',
])

describe('loading convention', () => {
  test('every force-dynamic page has a loading.tsx, or is listed debt', async () => {
    const missing: string[] = []
    const covered = new Set<string>()
    for (const rel of new Bun.Glob('**/page.tsx').scanSync(import.meta.dir)) {
      const abs = join(import.meta.dir, rel)
      const src = await Bun.file(abs).text()
      if (!src.includes("dynamic = 'force-dynamic'")) continue
      if (existsSync(join(dirname(abs), 'loading.tsx'))) {
        covered.add(rel)
      } else if (!KNOWN_UNCOVERED.has(rel)) {
        missing.push(rel)
      }
    }
    // New dynamic pages must ship a loading.tsx.
    expect(missing).toEqual([])
    // The debt list ratchets: a covered page must be removed from it.
    expect([...KNOWN_UNCOVERED].filter((rel) => covered.has(rel))).toEqual([])
  })
})

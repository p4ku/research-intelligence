import { describe, expect, test } from 'bun:test'
import { join } from 'node:path'

/**
 * Error-copy convention (error-UX audit #6): components never print a
 * problem's `title` or `detail`, or a stringified exception — they route
 * through `problemMessage()` / `errorsFromSubmit()` in src/lib/bff/problem-copy.ts,
 * where `/problems/validation` is the one slug whose human-written detail may
 * surface. A raw `detail` is operator material ("Django did not respond…")
 * and a raw `String(error)` is an exception dump ("TypeError: Failed to
 * fetch") — neither is product copy.
 */
// The receiver names a render site actually uses, with or without optional
// chaining; `String(error)` and its template-literal twin. Deliberately not
// `p.title`, which is a paper title on every browser page.
const BANNED = [
  /\b(problem|error|err)\??\.(detail|title)\b/,
  /String\((error|err)\)/,
  /\$\{(error|err)\}/,
]

// Route handlers under src/app/bff are producers, not render sites: they may
// log a problem's detail. Everything else under src/app and src/components
// — pages, layouts, hooks, client components, `.ts` and `.tsx` alike — is
// held to the convention.
const EXCLUDED = /^bff\//

describe('error copy convention', () => {
  test('no component renders problem.detail/title or String(error)', async () => {
    const roots = [join(import.meta.dir), join(import.meta.dir, '..', 'components')]
    const offenders: string[] = []
    for (const root of roots) {
      for (const rel of new Bun.Glob('**/*.{ts,tsx}').scanSync(root)) {
        if (rel.includes('.test.') || EXCLUDED.test(rel)) continue
        const src = await Bun.file(join(root, rel)).text()
        for (const pattern of BANNED) {
          if (pattern.test(src)) offenders.push(`${rel}: ${String(pattern)}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})

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
const BANNED = [/\bproblem\.(detail|title)\b/, /\berror\?\.(detail|title)\b/, /String\(error\)/]

describe('error copy convention', () => {
  test('no component renders problem.detail/title or String(error)', async () => {
    const roots = [join(import.meta.dir), join(import.meta.dir, '..', 'components')]
    const offenders: string[] = []
    for (const root of roots) {
      for (const rel of new Bun.Glob('**/*.tsx').scanSync(root)) {
        if (rel.includes('.test.')) continue
        const src = await Bun.file(join(root, rel)).text()
        for (const pattern of BANNED) {
          if (pattern.test(src)) offenders.push(`${rel}: ${String(pattern)}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})

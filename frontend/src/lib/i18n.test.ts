/**
 * Guards the German dictionary against silent drift. Keys are the English
 * source strings, so editing copy in a component quietly loses its German —
 * makeT falls back to English with only a dev-time console.warn. This test
 * makes that a failure:
 *  - every string passed to t() as a literal must exist in the dictionary
 *  - the same key must not carry two different values in two area modules
 *  - key and translation must use the same {placeholders}
 * Keys only reachable dynamically (t(x.label)) can't be verified statically;
 * unused ("dead") keys are reported but don't fail.
 */
import { describe, expect, test } from 'bun:test'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { de } from '../locales/de'
import { dict as ask } from '../locales/de/ask'
import { dict as briefing } from '../locales/de/briefing'
import { dict as chrome } from '../locales/de/chrome'
import { dict as components } from '../locales/de/components'
import { dict as dashboard } from '../locales/de/dashboard'
import { dict as errors } from '../locales/de/errors'
import { dict as login } from '../locales/de/login'
import { dict as papers } from '../locales/de/papers'
import { dict as settings } from '../locales/de/settings'
import { dict as tuning } from '../locales/de/tuning'

const SRC = join(import.meta.dir, '..')
const AREAS = {
  ask,
  briefing,
  chrome,
  components,
  dashboard,
  errors,
  login,
  papers,
  settings,
  tuning,
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name === 'locales') continue
      walk(p, out)
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) out.push(p)
  }
  return out
}

/** Drop comment-only lines so documentation examples don't count as calls. */
function stripComments(text: string): string {
  return text
    .split('\n')
    .filter((line) => {
      const lead = line.trimStart()
      return !lead.startsWith('//') && !lead.startsWith('*') && !lead.startsWith('/*')
    })
    .join('\n')
}

// t('x'), t("x"), t('x', 'ctx'), including multi-line calls with a trailing comma.
const CALL =
  /(?<![A-Za-z0-9_$.])t\(\s*(['"`])((?:\\.|(?!\1)[^\\])*)\1(?:\s*,\s*(['"])((?:\\.|(?!\3)[^\\])*)\3)?\s*,?\s*\)/g

function collectUses(): Map<string, string[]> {
  const uses = new Map<string, string[]>()
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    if (!/useT\(\)|getT\(\)|makeT\(|t\?: |t: T/.test(text)) continue
    for (const m of stripComments(text).matchAll(CALL)) {
      const s = m[2].replace(/\\(['"`])/g, '$1')
      const key = m[4] !== undefined ? `${m[4]}|${s}` : s
      uses.set(key, [...(uses.get(key) ?? []), relative(SRC, file)])
    }
  }
  return uses
}

const placeholders = (s: string) =>
  [...s.matchAll(/\{(\w+)\}/g)]
    .map((m) => m[1])
    .sort()
    .join(',')

describe('German dictionary', () => {
  const uses = collectUses()

  test('covers every statically used string', () => {
    const missing = [...uses].filter(([key]) => !(key in de))
    expect(missing.map(([key, files]) => `"${key}" (${[...new Set(files)].join(', ')})`)).toEqual(
      [],
    )
  })

  test('has no conflicting duplicates across area modules', () => {
    const seen = new Map<string, { area: string; value: string }[]>()
    for (const [area, dict] of Object.entries(AREAS))
      for (const [k, v] of Object.entries(dict))
        seen.set(k, [...(seen.get(k) ?? []), { area, value: v }])
    const conflicts = [...seen]
      .filter(([, v]) => new Set(v.map((x) => x.value)).size > 1)
      .map(
        ([k, v]) => `"${k}": ${v.map((x) => `${x.area}=${JSON.stringify(x.value)}`).join(' vs ')}`,
      )
    expect(conflicts).toEqual([])
  })

  test('keeps {placeholders} intact in every translation', () => {
    const broken = Object.entries(de)
      .filter(([k, v]) => placeholders(k.replace(/^[^|]+\|/, '')) !== placeholders(v))
      .map(([k, v]) => `"${k}" → "${v}"`)
    expect(broken).toEqual([])
  })

  test('reports (but tolerates) keys with no static caller', () => {
    const dead = Object.keys(de).filter((k) => !uses.has(k))
    if (dead.length > 0) {
      console.warn(
        `[i18n] ${dead.length} dictionary keys have no static t() caller ` +
          `(dynamic labels or dead prototype keys — see docs/i18n-backlog.md P1.7).`,
      )
    }
    expect(uses.size).toBeGreaterThan(100) // sanity: the scan actually found the app
  })
})

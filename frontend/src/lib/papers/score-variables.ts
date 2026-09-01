// Shapes `signal_score_details.variables` for display. Production values are
// whatever the extraction LLM produced: formula inputs (`fit_score: 82`),
// bands (`rigour_band: "Strong"`), paragraphs of assessment prose, and
// Python-repr lists serialised as strings (`"['a', 'b']"`). Pure; safe for
// client components.

import type { ScoreVariableValue } from '@/lib/bff/papers/schema'

export type VariableKind = 'number' | 'boolean' | 'short' | 'list' | 'text' | 'empty'

export interface ClassifiedVariable {
  key: string
  value: ScoreVariableValue
  kind: VariableKind
  /** Parsed items when `kind === 'list'`. */
  items?: string[]
}

export interface GroupedVariables {
  /** Read by the scoring snippet, in order of first use. */
  inputs: ClassifiedVariable[]
  /** Numbers, booleans and short labels the formula did not read. */
  scalars: ClassifiedVariable[]
  /** Lists and prose — the long tail. */
  long: ClassifiedVariable[]
}

// Above this a string stops reading as a label and is laid out as prose.
const SHORT_MAX = 24

const PYTHON_KEYWORDS = new Set([
  'and',
  'as',
  'assert',
  'break',
  'class',
  'continue',
  'def',
  'del',
  'elif',
  'else',
  'except',
  'False',
  'finally',
  'for',
  'from',
  'global',
  'if',
  'import',
  'in',
  'is',
  'lambda',
  'None',
  'nonlocal',
  'not',
  'or',
  'pass',
  'raise',
  'return',
  'True',
  'try',
  'while',
  'with',
  'yield',
  'round',
  'min',
  'max',
  'abs',
  'int',
  'float',
  'sum',
  'len',
])

/** Identifiers the snippet reads, in order of first appearance. Comments are skipped. */
export function formulaIdentifiers(code: string | null | undefined): string[] {
  if (!code) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const rawLine of code.split('\n')) {
    const line = rawLine.replace(/#.*$/, '')
    for (const m of line.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) {
      const id = m[0]
      if (PYTHON_KEYWORDS.has(id) || seen.has(id)) continue
      seen.add(id)
      out.push(id)
    }
  }
  return out
}

/**
 * `"['a', \"b\"]"` → `['a', 'b']`; anything that is not a single-level list of
 * quoted strings → null. Handles backslash escapes inside items.
 */
export function parsePythonList(s: string): string[] | null {
  const src = s.trim()
  if (src.length < 2 || src[0] !== '[' || src[src.length - 1] !== ']') return null
  const body = src.slice(1, -1).trim()
  if (body === '') return []
  const items: string[] = []
  let i = 0
  while (i < body.length) {
    const quote = body[i]
    if (quote !== "'" && quote !== '"') return null
    let j = i + 1
    let item = ''
    while (j < body.length && body[j] !== quote) {
      if (body[j] === '\\' && j + 1 < body.length) {
        item += body[j + 1]
        j += 2
      } else {
        item += body[j]
        j += 1
      }
    }
    if (j >= body.length) return null
    items.push(item)
    i = j + 1
    while (i < body.length && /\s/.test(body[i])) i++
    if (i < body.length) {
      if (body[i] !== ',') return null
      i++
      while (i < body.length && /\s/.test(body[i])) i++
    }
  }
  return items
}

export function classifyVariable(key: string, value: ScoreVariableValue): ClassifiedVariable {
  if (value === null || value === '') return { key, value, kind: 'empty' }
  if (typeof value === 'number') return { key, value, kind: 'number' }
  if (typeof value === 'boolean') return { key, value, kind: 'boolean' }
  const items = parsePythonList(value)
  if (items) return { key, value, kind: 'list', items }
  if (value.trim().length <= SHORT_MAX && !/[.!?]\s|\n/.test(value.trim())) {
    return { key, value, kind: 'short' }
  }
  return { key, value, kind: 'text' }
}

export function groupVariables(
  variables: Record<string, ScoreVariableValue>,
  code: string | null | undefined,
): GroupedVariables {
  const classified = Object.entries(variables).map(([k, v]) => classifyVariable(k, v))
  const byKey = new Map(classified.map((c) => [c.key, c]))
  const inputs: ClassifiedVariable[] = []
  for (const id of formulaIdentifiers(code)) {
    const hit = byKey.get(id)
    if (hit) {
      inputs.push(hit)
      byKey.delete(id)
    }
  }
  const rest = classified.filter((c) => byKey.has(c.key))
  return {
    inputs,
    scalars: rest.filter((c) => c.kind !== 'list' && c.kind !== 'text'),
    long: rest.filter((c) => c.kind === 'list' || c.kind === 'text'),
  }
}

const ACRONYMS = new Set(['trl', 'llm', 'ai', 'id', 'url', 'api', 'ml'])

/** `fit_score` → "Fit score", `trl_level` → "TRL level". Users never see snake_case. */
export function humanise(key: string): string {
  return key
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w, i) =>
      ACRONYMS.has(w.toLowerCase())
        ? w.toUpperCase()
        : i === 0
          ? w[0].toUpperCase() + w.slice(1)
          : w,
    )
    .join(' ')
}

/** Display form for scalar kinds; lists/prose are laid out by the component. */
export function formatVariable(v: ClassifiedVariable, t: (s: string) => string = (s) => s): string {
  switch (v.kind) {
    case 'empty':
      return '—'
    case 'number': {
      const n = v.value as number
      return Number.isInteger(n) ? String(n) : (Math.round(n * 100) / 100).toString()
    }
    case 'boolean':
      return v.value ? t('Yes') : t('No')
    default:
      return String(v.value)
  }
}

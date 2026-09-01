// The signal-score formula is a backend-owned Python snippet, but users must
// never see code. So the UI decomposes the score itself — from a TypeScript
// mirror of the one snippet in production — and only when it can prove the
// mirror applies: the snippet text is recognised AND re-evaluating the
// recorded inputs reproduces the stored score. Otherwise callers fall back to
// showing the inputs without a breakdown. Pure; safe for client components.
//
//   if trl_level < 3.0:
//       return 0.0
//   base = 0.6 * fit_score + 0.4 * novelty_score
//   multiplier = 1.25 if trl_level >= 7.0 else 1.0
//   return round(base * multiplier, 2)

import type { ScoreVariableValue } from '@/lib/bff/papers/schema'

export interface Inputs {
  trl: number
  fit: number
  novelty: number
}

export const GATE_TRL = 3
export const BONUS_TRL = 7
export const FIT_WEIGHT = 0.6
export const NOVELTY_WEIGHT = 0.4
export const BONUS = 1.25

/** Variable key → input, as the snippet names them. */
export const INPUT_IDS: Record<keyof Inputs, string> = {
  trl: 'trl_level',
  fit: 'fit_score',
  novelty: 'novelty_score',
}

const CANON = [
  'if trl_level < 3.0:',
  'return 0.0',
  'base = 0.6 * fit_score + 0.4 * novelty_score',
  'multiplier = 1.25 if trl_level >= 7.0 else 1.0',
  'return round(base * multiplier, 2)',
]

/** True when the snippet is, modulo comments and whitespace, the one mirrored here. */
export function recognisedSnippet(code: string | null | undefined): boolean {
  if (!code) return false
  const lines = code
    .split('\n')
    .map((l) => l.replace(/#.*$/, '').trim().replace(/\s+/g, ' '))
    .filter(Boolean)
  return lines.length === CANON.length && lines.every((l, i) => l === CANON[i])
}

export function round2(n: number): number {
  return Math.round(n * 100) / 100
}

export function readInputs(
  vars: Record<string, ScoreVariableValue> | null | undefined,
): Inputs | null {
  if (!vars) return null
  const num = (k: string): number | null => {
    const v = vars[k]
    if (typeof v === 'number') return v
    if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return Number(v)
    return null
  }
  const trl = num(INPUT_IDS.trl)
  const fit = num(INPUT_IDS.fit)
  const novelty = num(INPUT_IDS.novelty)
  if (trl === null || fit === null || novelty === null) return null
  return { trl, fit, novelty }
}

export interface Evaluation {
  gate: boolean
  fitPart: number
  noveltyPart: number
  base: number
  multiplier: number
  bonus: number
  score: number
}

export function evaluate(i: Inputs): Evaluation {
  // Parts are rounded to what is displayed, so 0.6 × 82 reads 49.2, not 49.199999….
  const gate = i.trl >= GATE_TRL
  const fitPart = round2(FIT_WEIGHT * i.fit)
  const noveltyPart = round2(NOVELTY_WEIGHT * i.novelty)
  const base = round2(fitPart + noveltyPart)
  const multiplier = i.trl >= BONUS_TRL ? BONUS : 1
  const bonus = round2(base * (multiplier - 1))
  const score = gate ? round2(base * multiplier) : 0
  return { gate, fitPart, noveltyPart, base, multiplier, bonus, score }
}

/**
 * The inputs to decompose `score` with — or null when the mirror cannot be
 * trusted for this record (unknown snippet, missing inputs, or a mismatch).
 */
export function ledgerInputs(
  code: string | null | undefined,
  vars: Record<string, ScoreVariableValue> | null | undefined,
  score: number | null,
): Inputs | null {
  if (score === null || !recognisedSnippet(code)) return null
  const inputs = readInputs(vars)
  if (!inputs) return null
  return Math.abs(evaluate(inputs).score - score) < 0.011 ? inputs : null
}

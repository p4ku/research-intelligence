// The workspace-level view of what steers the ranking: which dimensions the
// signal score weighs, and how much. Same honesty rule as the per-paper ledger
// — the shares are read off the mirror in signal-formula.ts, and only when that
// mirror is provably the formula this workspace ran (snippet recognised AND
// re-evaluating a real scored paper's recorded inputs reproduces its stored
// score). When the proof fails, callers get null and must show the dimension
// names without any influence claim. Pure; safe for client components.

import type { WorkspaceScoring } from '@/lib/bff/scoring/schema'
import {
  BONUS,
  BONUS_TRL,
  FIT_WEIGHT,
  GATE_TRL,
  INPUT_IDS,
  NOVELTY_WEIGHT,
  ledgerInputs,
} from './signal-formula'

export interface Influence {
  key: keyof typeof INPUT_IDS
  /** The variable name as the snippet knows it, e.g. 'fit_score'. */
  variable: string
  label: string
  /**
   * 'share' — a fixed proportion of the base score.
   * 'gate'  — not a weight at all: a floor below which the score is 0, plus a
   *           multiplier above a threshold. Never render this as a percentage.
   */
  kind: 'share' | 'gate'
  /** Proportion of the base, 0–1. Null for the gate. */
  share: number | null
  /** Below this the score is 0. Null for shares. */
  gate: number | null
  /** At or above this the base is multiplied. Null for shares. */
  bonusAt: number | null
  /** The multiplier applied at `bonusAt`. Null for shares. */
  bonus: number | null
}

/**
 * What the workspace's score weighs — or null when the mirror cannot be proven
 * for this workspace, in which case no influence may be shown.
 */
export function tuningProfile(scoring: WorkspaceScoring): Influence[] | null {
  const proven = ledgerInputs(
    scoring.code,
    scoring.example?.variables,
    scoring.example?.signal_score ?? null,
  )
  if (!proven) return null

  return [
    {
      key: 'fit',
      variable: INPUT_IDS.fit,
      label: 'Fit score',
      kind: 'share',
      share: FIT_WEIGHT,
      gate: null,
      bonusAt: null,
      bonus: null,
    },
    {
      key: 'novelty',
      variable: INPUT_IDS.novelty,
      label: 'Novelty score',
      kind: 'share',
      share: NOVELTY_WEIGHT,
      gate: null,
      bonusAt: null,
      bonus: null,
    },
    {
      key: 'trl',
      variable: INPUT_IDS.trl,
      label: 'TRL level',
      kind: 'gate',
      share: null,
      gate: GATE_TRL,
      bonusAt: BONUS_TRL,
      bonus: BONUS,
    },
  ]
}

/** The dimension names to fall back to when the profile cannot be proven. */
export function fallbackDimensions(scoring: WorkspaceScoring): string[] {
  return scoring.variables.map((v) => v.name)
}

// The one rule for score-like numbers, decided with the stakeholder on 10 Sep
// 2026 (Question Relay /adam/rounding):
//
//   - the Schwarz Score and its sub-scores read as whole numbers everywhere;
//   - thresholds, sorts and filters compare the EXACT stored value — display
//     rounds, nothing else does (74.96 shows "75" and is not ≥ 75);
//   - a score never exceeds 100;
//   - TRL is always a whole number, 1–9;
//   - a paper whose formula failed is not scored — never a number.
//
// This module is pure so the BFF parse seam, the mapper and any client
// component can share it. The display half lives in `select.ts`
// (`formatScore`, `formatMeasure`), since it needs the locale.

export const SCORE_CEILING = 100
// One point per step: the stakeholder asked for a 1-point slider on 10 Sep
// 2026 (it was five).
export const SCORE_STEP = 1

/** The stored value held to the 0–100 scale the whole UI assumes. */
export const clampScore = (n: number): number => Math.min(SCORE_CEILING, Math.max(0, n))

/**
 * The Schwarz Score a reader may see: `null` unless the backend sent a finite
 * number, `null` when the formula recorded an error (the scorer writes 0.0 on
 * failure, and only `signal_score_details.error` tells that apart from a real
 * zero), otherwise the exact value capped at 100.
 */
export function signalScoreOf(
  score: unknown,
  details?: { error?: string | null } | null,
): number | null {
  if (typeof score !== 'number' || !Number.isFinite(score)) return null
  if (typeof details?.error === 'string' && details.error.trim() !== '') return null
  return clampScore(score)
}

/** A TRL as the scale defines it: a whole number from 1 to 9. */
export const trlLevel = (n: number): number => Math.min(9, Math.max(1, Math.round(n)))

/**
 * A dimension as the UI may hold it. Only TRL is coerced: other dimensions
 * keep their exact value, since their `max` is inferred and can legitimately
 * be exceeded (the bars clamp visually; the figure prints as it is).
 */
export function normaliseDimension<D extends { value: number | null; is_trl: boolean }>(d: D): D {
  if (!d.is_trl || d.value === null || !Number.isFinite(d.value)) return d
  const level = trlLevel(d.value)
  return level === d.value ? d : { ...d, value: level }
}

/** A paper with its Schwarz Score held to the rule above. */
export function normaliseScore<
  P extends {
    signal_score: number | null
    signal_score_details?: { error?: string | null } | null
  },
>(p: P): P {
  const score = signalScoreOf(p.signal_score, p.signal_score_details)
  return score === p.signal_score ? p : { ...p, signal_score: score }
}

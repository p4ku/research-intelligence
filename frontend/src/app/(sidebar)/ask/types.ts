// View types for the Ask console. Data comes from the chat BFF contract
// (src/lib/bff/chat/schema.ts); these shapes add the presentation snapshot a
// transcript needs (asked-at time, the scope's display title at ask time).

import type { ChatUsage, FactCheck, PaperCitation, VisualCitation } from '@/lib/bff/chat/schema'
import type { PaletteEntry } from '@/lib/bff/papers/schema'

/** A picker row — the papers contract's slim projection, served by /bff/papers/palette. */
export type { PaletteEntry }

/**
 * What the composer is attached to: the little a chip needs. A picker row
 * is one; so is a paper resolved on its own (a deep link, a reopened thread)
 * before the corpus has arrived.
 */
export type ScopeTarget = Pick<PaletteEntry, 'id' | 'title' | 'signal_score'>

/**
 * What the question was aimed at, captured at ask time. Conversations are
 * always scoped to one paper; null survives only for sessions filed before
 * whole-corpus asking was hidden.
 */
export interface AskScope {
  paper_id: string | null
  /** Display title of the paper (survives papers leaving the workspace). */
  title: string | null
}

export interface QuestionTurn {
  kind: 'question'
  text: string
  /** 'HH:MM' local time. */
  askedAt: string
  scope: AskScope
}

export interface AnswerTurn {
  kind: 'answer'
  text: string
  citations: PaperCitation[]
  visualCitations: VisualCitation[]
  factCheck: FactCheck | null
  usage: ChatUsage | null
  /** Problem title/detail when the turn failed. */
  error: string | null
  /** Settled from a live stream in this view (its extras arrive with motion). */
  arrived?: boolean
  /** The reader stopped the stream; the text is what had arrived. */
  stopped?: boolean
}

/** A bare target change, rendered as a quiet centered line in the transcript. */
export interface TargetTurn {
  kind: 'target'
  scope: AskScope
}

export type Turn = QuestionTurn | AnswerTurn | TargetTurn

/** Everywhere a paper is named in tight space, the pre-colon title stands in. */
export { shortTitle } from '@/lib/papers/select'

export const timeOf = (iso: string) => {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// View types for the Ask console. Data comes from the chat BFF contract
// (src/lib/bff/chat/schema.ts); these shapes add the presentation snapshot a
// transcript needs (asked-at time, the scope's display title at ask time).

import type { ChatUsage, FactCheck, PaperCitation, VisualCitation } from '@/lib/bff/chat/schema'

/** A picker row / scope target — a slim projection of ScoredPaper. */
export interface PaletteEntry {
  id: string
  title: string
  first_author: string | null
  source: string
  signal_score: number | null
  created_at: string
}

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
export const shortTitle = (title: string) => title.split(':')[0]

export const timeOf = (iso: string) => {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

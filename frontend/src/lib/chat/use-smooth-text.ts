'use client'

/**
 * Smooth reveal for streamed text: the network hands us chunks of any size
 * at any rhythm; the reader sees one word at a time at a steady cadence that
 * quickens as the backlog grows, so the reveal never falls far behind arrival
 * and never stutters with it. Pure helpers are exported for tests.
 */
import { useEffect, useState } from 'react'
import type { ChatStreamStatus } from './use-chat-stream'

/**
 * Index just past the next complete word (its trailing whitespace included)
 * at or after `from`, or null when the text ends mid-word — the word is still
 * being written, so wait for more.
 */
export function nextWordEnd(text: string, from: number): number | null {
  const match = /^\s*\S+\s+/.exec(text.slice(from))
  return match ? from + match[0].length : null
}

/** Milliseconds until the next word, by how much text is still waiting. */
export function cadence(backlogChars: number, finished: boolean): number {
  if (finished) return 28
  if (backlogChars > 600) return 12
  if (backlogChars > 250) return 24
  if (backlogChars > 80) return 40
  return 60
}

export function useSmoothText(
  text: string,
  status: ChatStreamStatus,
): { text: string; caughtUp: boolean } {
  // Mount one instance per stream (key it on the question) — the reveal
  // position is never reset, only clamped.
  const [revealed, setRevealed] = useState(0)
  const shown = Math.min(revealed, text.length)
  const finished = status === 'done' || status === 'error'

  useEffect(() => {
    if (shown >= text.length) return
    // Once the stream has finished, the last word needs no trailing space.
    const next = nextWordEnd(text, shown) ?? (finished ? text.length : null)
    if (next === null) return
    const id = window.setTimeout(() => setRevealed(next), cadence(text.length - shown, finished))
    return () => window.clearTimeout(id)
  }, [text, shown, finished])

  return { text: text.slice(0, shown), caughtUp: shown >= text.length }
}

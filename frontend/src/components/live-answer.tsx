'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import type { ChatStreamState } from '@/lib/chat/use-chat-stream'
import { useSmoothText } from '@/lib/chat/use-smooth-text'
import { useT } from '@/lib/i18n-client'
import { useEffect, useState, type ReactNode } from 'react'

/**
 * The in-flight half of a chat turn, shared by the Ask console and the paper
 * sidecar: streamed text is revealed at a steady word cadence and each word
 * unveils out of a blur; a scanning line holds until the first word. The
 * transcript settles the turn once `onRevealed` reports that the stream has
 * finished and every word is on screen — either can come first, so the
 * caller keeps both flags and commits when the second lands.
 */

function useElapsed(active: boolean) {
  const [ms, setMs] = useState(0)
  useEffect(() => {
    if (!active) return
    const t0 = performance.now()
    const id = window.setInterval(() => setMs(performance.now() - t0), 100)
    return () => window.clearInterval(id)
  }, [active])
  return ms
}

/** Retrieval status shown until the first word arrives, with the wait counted. */
export function ScanningLine({ children }: { children: ReactNode }) {
  const ms = useElapsed(true)
  return (
    <p className="mt-1 flex items-center gap-2 font-mono text-xs text-muted-foreground tabular-nums">
      <span className="relative flex size-2 shrink-0">
        <span className="absolute inset-0 animate-ping rounded-full bg-accent/60" />
        <span className="relative size-2 rounded-full bg-accent" />
      </span>
      <span className="min-w-0 truncate">{children}</span>
      <span className="ml-auto shrink-0">{(ms / 1000).toFixed(1)}s</span>
    </p>
  )
}

export function LiveAnswer({
  state,
  scanning,
  className,
  onGrow,
  onRevealed,
}: {
  state: ChatStreamState
  /** What the scanning line says while no word has arrived yet. */
  scanning: ReactNode
  /** Size and ink for the surface, e.g. `text-[15px] text-foreground`. */
  className?: string
  /** Called as words land, so the transcript can follow. */
  onGrow: () => void
  /** The stream has finished and the reveal has caught up with it. */
  onRevealed: () => void
}) {
  const t = useT()
  const shown = useSmoothText(state.text, state.status)
  const finished = state.status === 'done' || state.status === 'error'

  useEffect(() => {
    if (shown.text) onGrow()
  }, [shown.text, onGrow])

  useEffect(() => {
    if (finished && shown.caughtUp) onRevealed()
  }, [finished, shown.caughtUp, onRevealed])

  if (state.status === 'idle') return null
  if (shown.text === '') return <ScanningLine>{scanning}</ScanningLine>
  // Visual citations land after the last delta, so chips render without ticks
  // until then.
  return (
    <AnswerMarkdown
      text={shown.text}
      streaming
      unveil
      caret={false}
      citations={state.visualCitations}
      t={t}
      className={className}
    />
  )
}

import { forPage } from '@/lib/bff/core/page'
import { isUuid } from '@/lib/bff/core/validate'
import { papers } from '@/lib/bff/papers/service'
import { Ask } from './ask'
import type { ScopeTarget } from './types'

/**
 * The console itself needs nothing from Django to paint: the corpus behind
 * the picker and the session history behind the sidecar both arrive after
 * mount (see ./use-palette.ts and the history effect in ./ask.tsx). Only a
 * deep link to one paper is resolved here — one scorecard read, so the chip
 * is attached before the first keystroke, not the whole corpus.
 */
export async function AskSection({
  paper,
  session,
  question,
}: {
  paper?: string
  session?: string
  /** Home's search, handed over as the first question (never sent on its own). */
  question?: string
}) {
  // A link to a paper that is not (or no longer) visible opens a plain console.
  const found = paper && isUuid(paper) ? await forPage(papers.get(paper)) : null
  const initialTarget: ScopeTarget | null = found
    ? { id: found.paper.id, title: found.paper.title, signal_score: found.paper.signal_score }
    : null
  const initialQuestion = question?.trim().slice(0, 200) || undefined

  return (
    <Ask
      key={`${initialTarget?.id ?? 'none'}:${initialQuestion ?? ''}`}
      initialTarget={initialTarget}
      initialSessionId={session && isUuid(session) ? session : undefined}
      initialQuestion={initialQuestion}
    />
  )
}

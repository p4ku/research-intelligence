import { chat } from '@/lib/bff/chat/service'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import { byValueDesc } from '@/lib/papers/select'
import { Ask } from './ask'
import type { PaletteEntry } from './types'

/**
 * The console behind its Suspense boundary: the corpus (for the picker) and
 * the session history both block it, so they stream together while the
 * page's header and the console skeleton are already on screen.
 */
export async function AskSection({
  wsId,
  paper,
  session,
}: {
  wsId: string
  paper?: string
  session?: string
}) {
  const [scored, sessions] = await forPage(
    Promise.all([
      papers.listAll(wsId),
      chat.listSessions({ workspace_id: wsId, page: 1, page_size: 100 }),
    ]),
  )

  const entries: PaletteEntry[] = (scored?.papers ?? [])
    .map((p) => ({
      id: p.id,
      title: p.title,
      first_author: p.authors[0] ?? null,
      source: p.source,
      signal_score: p.signal_score,
      created_at: p.created_at,
    }))
    .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))

  const initialPaperId = paper && entries.some((e) => e.id === paper) ? paper : undefined

  return (
    <Ask
      key={`${wsId}:${initialPaperId ?? 'none'}`}
      workspaceId={wsId}
      entries={entries}
      initialSessions={sessions.results}
      initialPaperId={initialPaperId}
      initialSessionId={session}
    />
  )
}

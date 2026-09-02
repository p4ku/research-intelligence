import { Card, PageHeader } from '@/components/scanner-ui'
import { chat } from '@/lib/bff/chat/service'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import { getT } from '@/lib/i18n-server'
import { byValueDesc } from '@/lib/papers/select'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { Ask } from './ask'
import type { PaletteEntry } from './types'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Ask the scanner') }
}

export default async function AskPage({
  searchParams,
}: {
  searchParams: Promise<{ paper?: string; session?: string }>
}) {
  const [t, ws, { paper, session }] = await Promise.all([
    getT(),
    getCurrentWorkspace(),
    searchParams,
  ])

  if (!ws) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Assistant')} title={t('Ask Research Intelligence')} />
        <Card>
          <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
            {t('No workspace selected')}
          </p>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {t('You are not a member of any workspace yet. Ask an administrator for access.')}
          </p>
        </Card>
      </div>
    )
  }

  const [scored, sessions] = await forPage(
    Promise.all([
      papers.listAll(ws.id),
      chat.listSessions({ workspace_id: ws.id, page: 1, page_size: 100 }),
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

  // The console owns the viewport: the page does not scroll, the transcript does.
  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col gap-6 lg:h-[calc(100dvh-6rem)]">
      <div className="shrink-0">
        <PageHeader eyebrow={t('Assistant')} title={t('Ask Research Intelligence')} />
      </div>
      <Ask
        key={`${ws.id}:${initialPaperId ?? 'none'}`}
        workspaceId={ws.id}
        entries={entries}
        initialSessions={sessions.results}
        initialPaperId={initialPaperId}
        initialSessionId={session}
      />
    </div>
  )
}

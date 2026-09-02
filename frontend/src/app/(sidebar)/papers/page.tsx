import { Card, PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import { fmt } from '@/lib/i18n'
import { getT } from '@/lib/i18n-server'
import { getWorkspaceState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { PapersBrowser } from './papers-browser'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Papers') }
}

export default async function PapersPage() {
  const [t, state] = await Promise.all([getT(), getWorkspaceState()])

  if (state.kind !== 'ok') {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Corpus')} title={t('Papers')} />
        <WorkspaceNotice kind={state.kind} />
      </div>
    )
  }

  // The membership list said this workspace exists; a null corpus means the
  // workspace itself was not visible (gone, or access revoked in between).
  // That is an absence, not a membership fact — the 404 page says so.
  const scored = await forPage(papers.listAll(state.ws.id))
  if (!scored) notFound()

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={scored.workspace.name} title={t('Papers')} />
      {scored.papers.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {fmt(t('No papers in {workspace} yet.'), { workspace: scored.workspace.name })}
          </p>
        </Card>
      ) : (
        <PapersBrowser papers={scored.papers} workspace={scored.workspace} />
      )}
    </div>
  )
}

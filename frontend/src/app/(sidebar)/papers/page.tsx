import { Card, PageHeader } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import { fmt } from '@/lib/i18n'
import { getT } from '@/lib/i18n-server'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { PapersBrowser } from './papers-browser'

export const metadata: Metadata = { title: 'Papers' }
export const dynamic = 'force-dynamic'

export default async function PapersPage() {
  const [t, ws] = await Promise.all([getT(), getCurrentWorkspace()])
  const scored = ws ? await forPage(papers.listAll(ws.id)) : null

  if (!ws || !scored) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Corpus')} title={t('Papers')} />
        <Card>
          <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
            {t('No workspace selected')}
          </p>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {t('You are not a member of any workspace yet. Membership is managed in the backend.')}
          </p>
        </Card>
      </div>
    )
  }

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

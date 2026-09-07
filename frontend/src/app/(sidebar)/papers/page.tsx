import { Card, PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import { hasFeature, requireFeature } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { PapersBrowser } from './papers-browser'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  // generateMetadata runs independently of the page body, so it needs its own
  // gate: without it the 404's tab and history entry would still read "Papers".
  if (!(await hasFeature('all_papers'))) return {}
  const t = await getT()
  return { title: t('Papers') }
}

/**
 * Every paper from every domain the user belongs to, one browser over all of
 * them. `?q=` is Home's search, pre-filled into the browser's field.
 *
 * Behind the `all_papers` demo flag: off, the route does not exist. The gate is
 * the first statement, above the workspace check, so a hidden page 404s even
 * during an outage. No `loading.tsx` here (the `--stream` negative control in
 * docs/skeletons.md), which is what makes that a genuine HTTP 404.
 */
export default async function PapersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>
}) {
  await requireFeature('all_papers')
  const [t, state, { q }] = await Promise.all([getT(), getWorkspacesState(), searchParams])

  if (state.kind !== 'ok') {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Corpus')} title={t('Papers')} />
        <WorkspaceNotice kind={state.kind} />
      </div>
    )
  }

  const corpus = await forPage(papers.listEverywhere())
  // One domain reads as itself; several read as the whole corpus, with the
  // domain filter in the browser doing the narrowing.
  const eyebrow = corpus.workspaces.length === 1 ? corpus.workspaces[0].name : t('All domains')

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={eyebrow} title={t('Papers')} />
      {corpus.papers.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">{t('No papers yet.')}</p>
        </Card>
      ) : (
        <PapersBrowser
          key={q ?? ''}
          papers={corpus.papers}
          workspaces={corpus.workspaces}
          initialSearch={q?.trim() ?? ''}
        />
      )}
    </div>
  )
}

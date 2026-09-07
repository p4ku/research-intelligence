import { Card } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import type { T } from '@/lib/i18n'
import { PapersBrowser } from './papers-browser'

/**
 * The browser behind its Suspense boundary: every paper from every domain,
 * or the empty card. One root element — the page wraps it in a
 * <ViewTransition> pair with its skeleton.
 */
export async function PapersSection({ t, q }: { t: T; q?: string }) {
  const corpus = await forPage(papers.listEverywhere())
  if (corpus.papers.length === 0) {
    return (
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">{t('No papers yet.')}</p>
      </Card>
    )
  }
  return (
    <PapersBrowser
      key={q ?? ''}
      papers={corpus.papers}
      workspaces={corpus.workspaces}
      initialSearch={q?.trim() ?? ''}
    />
  )
}

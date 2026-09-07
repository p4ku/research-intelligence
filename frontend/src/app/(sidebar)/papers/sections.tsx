import { Card } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import type { T } from '@/lib/i18n'
import { toPapersQuery, type BrowseState } from '@/lib/papers/browse'
import { PapersBrowser } from './papers-browser'

/**
 * The browser behind its Suspense boundary: the first page for the URL's
 * state, with the rail's facets, or the empty card. One root element — the
 * page wraps it in a <ViewTransition> pair with its skeleton. No `key`: the
 * browser reads the URL itself and updates in place, keeping the rail's open
 * groups and the search field's focus across every change.
 */
export async function PapersSection({
  t,
  state,
  domains,
}: {
  t: T
  state: BrowseState
  domains: { id: string; name: string }[]
}) {
  const list = await forPage(papers.list(toPapersQuery(state)))
  if (list.facets.total === 0) {
    return (
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">{t('No papers yet.')}</p>
      </Card>
    )
  }
  return <PapersBrowser served={{ state, list }} domains={domains} />
}

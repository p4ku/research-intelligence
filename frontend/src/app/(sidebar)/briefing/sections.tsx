import { Card } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { runs } from '@/lib/bff/pipeline-runs/service'
import type { Lang, T } from '@/lib/i18n'
import type { WorkspaceSummary } from '@/lib/papers/types'
import { BriefingLedger } from './briefing-ledger'
import { composeRows, searchOf, type ArchiveState } from './rows'
import { domainNames } from './scope'

/**
 * The archive behind its Suspense boundary: every edition of every domain,
 * joined to the runs that produced them, or the empty card. Asking for the
 * completed runs shares the fetch the briefings service already made.
 */
export async function LedgerSection({
  workspaces,
  initial,
  lang,
  t,
}: {
  workspaces: WorkspaceSummary[]
  initial: ArchiveState
  lang: Lang
  t: T
}) {
  const [editions, completed] = await forPage(
    Promise.all([briefings.listEverywhere(lang), runs.listEverywhere('completed')]),
  )

  if (editions.length === 0) {
    return (
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('No briefings have been generated yet.')}
        </p>
      </Card>
    )
  }

  const rows = composeRows({ editions, runs: completed, domains: domainNames(workspaces), t, lang })
  return (
    // Keyed on the query: a Back navigation to a different filter or page
    // remounts the ledger in that state; a refresh on the same URL keeps it.
    <BriefingLedger
      key={searchOf(initial)}
      rows={rows}
      domains={workspaces.map(({ id, name }) => ({ id, name }))}
      initial={initial}
    />
  )
}

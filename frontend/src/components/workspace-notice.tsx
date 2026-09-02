import { Card } from '@/components/scanner-ui'
import { RefreshButton } from '@/components/workspace-notice-retry'
import { problemMessage } from '@/lib/bff/problem-copy'
import { getT } from '@/lib/i18n-server'
import type { WorkspaceState } from '@/lib/workspace-server'
import { ExclamationTriangleIcon } from '@heroicons/react/16/solid'

/**
 * The card a page renders when it has no workspace to show. Two distinct
 * states that must never converge (error-UX audit #2):
 *  - `none`: the user belongs to no workspace — an account fact, membership copy.
 *  - `unavailable`: the workspace list could not be fetched — an outage,
 *    with a Retry. Never the membership copy. The second line is the mapped
 *    copy for the problem that actually occurred, so a backend that did not
 *    answer and a backend whose payload stopped matching the contract read
 *    differently — the 2026-09-02 `digest_schedule` incident showed
 *    "Couldn't reach the backend" for a reachable backend on every page.
 * Studio pages pass `english` (operator surface, untranslated by decision).
 */
export async function WorkspaceNotice({
  state,
  english = false,
}: {
  state: Exclude<WorkspaceState, { kind: 'ok' }>
  english?: boolean
}) {
  const t = english ? (s: string) => s : await getT()

  if (state.kind === 'none') {
    return (
      <Card>
        <p className="text-foreground text-sm font-medium">{t('No workspace selected')}</p>
        <p className="text-muted-foreground mt-1 text-sm">
          {t('You are not a member of any workspace yet. Ask an administrator for access.')}
        </p>
      </Card>
    )
  }

  return (
    <Card role="alert">
      <div className="flex items-start gap-2.5">
        <ExclamationTriangleIcon
          aria-hidden="true"
          className="text-negative mt-0.5 size-4 shrink-0"
        />
        <div className="min-w-0">
          <p className="text-foreground text-sm font-medium">
            {t("Couldn't load your workspaces.")}
          </p>
          <p className="text-muted-foreground mt-1 text-sm">{problemMessage(state.problem, t)}</p>
          <div className="mt-4">
            <RefreshButton label={t('Retry')} busyLabel={t('Retrying…')} />
          </div>
        </div>
      </div>
    </Card>
  )
}

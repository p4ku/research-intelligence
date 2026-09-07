import { Card } from '@/components/scanner-ui'
import { RefreshButton } from '@/components/workspace-notice-retry'
import { getT } from '@/lib/i18n-server'
import { ExclamationTriangleIcon } from '@heroicons/react/16/solid'

/**
 * The card a page renders when it has no domain to read from. Two distinct
 * states that must never converge (error-UX audit #2):
 *  - `none`: the user belongs to no workspace — an account fact, membership copy.
 *  - `unavailable`: the workspace list could not be fetched — an outage,
 *    named as such, with a Retry. Never the membership copy.
 * English-only pages pass `english` (operator copy, untranslated by decision).
 */
export async function WorkspaceNotice({
  kind,
  english = false,
}: {
  kind: 'none' | 'unavailable'
  english?: boolean
}) {
  const t = english ? (s: string) => s : await getT()

  if (kind === 'none') {
    return (
      <Card>
        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {t('No domains yet')}
        </p>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {t("You don't have access to any domain yet. Ask an administrator for access.")}
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
          <p className="text-foreground text-sm font-medium">{t("Couldn't reach the backend.")}</p>
          <p className="text-muted-foreground mt-1 text-sm">
            {t('Nothing was lost. Try again in a moment.')}
          </p>
          <div className="mt-4">
            <RefreshButton label={t('Retry')} busyLabel={t('Retrying…')} />
          </div>
        </div>
      </div>
    </Card>
  )
}

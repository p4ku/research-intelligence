import { Card } from '@/components/scanner-ui'
import { getT } from '@/lib/i18n-server'
import Link from 'next/link'

/**
 * Root 404 — the only one a URL that matched no route at all can reach, since
 * the (sidebar) and studio not-founds need their own segment to match first.
 * Without it every mistyped URL got Next's built-in page: unstyled, English,
 * and no way back.
 *
 * It renders in the root layout, so there is no shell around it — hence the
 * centred card rather than in-page chrome. Middleware sends signed-out
 * visitors to /?next=… before they ever get here, so whoever reads this has a
 * session and the dashboard is the way back.
 */
export default async function NotFound() {
  const t = await getT()

  return (
    <div className="mx-auto max-w-lg px-6 pt-24">
      <Card>
        <p className="text-sm font-medium text-foreground">{t("We couldn't find that.")}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t('It may have been removed, or the link may be out of date.')}
        </p>
        <div className="mt-4 flex items-center gap-3">
          <Link
            href="/dashboard"
            className="rounded-sm bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
          >
            {t('Go to Dashboard')}
          </Link>
          <Link
            href="/papers"
            className="rounded-sm border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:bg-line-soft/60"
          >
            {t('Go to Papers')}
          </Link>
        </div>
      </Card>
    </div>
  )
}

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
        <p className="text-foreground text-sm font-medium">{t("We couldn't find that.")}</p>
        <p className="text-muted-foreground mt-1 text-sm">
          {t('It may have been removed, or the link may be out of date.')}
        </p>
        <div className="mt-4 flex items-center gap-3">
          <Link
            href="/dashboard"
            className="bg-foreground text-background hover:bg-foreground/85 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors"
          >
            {t('Go to Dashboard')}
          </Link>
          <Link
            href="/papers"
            className="border-line hover:bg-line-soft/60 rounded-sm border px-3 py-1.5 text-sm font-medium transition-colors"
          >
            {t('Go to Papers')}
          </Link>
        </div>
      </Card>
    </div>
  )
}

import { Card } from '@/components/scanner-ui'
import { getT } from '@/lib/i18n-server'
import Link from 'next/link'

/** Segment-scoped 404 inside the Studio shell. Same three sentences as the
 *  reading app's 404, so it follows the language cookie the same way. */
export default async function NotFound() {
  const t = await getT()
  return (
    <div className="mx-auto max-w-lg pt-16">
      <Card>
        <p className="text-sm font-medium text-foreground">{t("We couldn't find that.")}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t('It may have been removed, or the link may be out of date.')}
        </p>
        <div className="mt-4">
          <Link
            href="/runs"
            className="rounded-sm bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
          >
            {t('Back to Runs')}
          </Link>
        </div>
      </Card>
    </div>
  )
}

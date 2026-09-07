import { Card } from '@/components/scanner-ui'
import { getFeatures } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import clsx from 'clsx'
import Link from 'next/link'

const PRIMARY =
  'rounded-sm bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85'
const SECONDARY =
  'rounded-sm border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:bg-line-soft/60'

/**
 * Segment-scoped 404: renders inside the sidebar shell so the switcher and
 * account menu survive, unlike Next's built-in page. Deliberately generic —
 * it serves papers, briefings, and the screening log alike. It is also where
 * a hidden route lands, so with the Papers list switched off it must not
 * offer a button to another 404: Briefings takes the primary slot instead.
 */
export default async function NotFound() {
  const [t, features] = await Promise.all([getT(), getFeatures()])

  return (
    <div className="mx-auto max-w-lg pt-16">
      <Card>
        <p className="text-sm font-medium text-foreground">{t("We couldn't find that.")}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t('It may have been removed, or the link may be out of date.')}
        </p>
        <div className="mt-4 flex items-center gap-3">
          {features.all_papers && (
            <Link href="/papers" className={PRIMARY}>
              {t('Go to Papers')}
            </Link>
          )}
          <Link href="/briefing" className={clsx(features.all_papers ? SECONDARY : PRIMARY)}>
            {t('Go to Briefings')}
          </Link>
        </div>
      </Card>
    </div>
  )
}

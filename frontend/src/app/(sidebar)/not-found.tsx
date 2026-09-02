import { Card } from '@/components/scanner-ui'
import { getT } from '@/lib/i18n-server'
import Link from 'next/link'

/**
 * Segment-scoped 404: renders inside the sidebar shell so the switcher and
 * account menu survive, unlike Next's built-in page. Deliberately generic —
 * it serves papers, briefings, and the screening log alike.
 */
export default async function NotFound() {
  const t = await getT()

  return (
    <div className="mx-auto max-w-lg pt-16">
      <Card>
        <p className="text-foreground text-sm font-medium">{t("We couldn't find that.")}</p>
        <p className="text-muted-foreground mt-1 text-sm">
          {t('It may have been removed, or the link may be out of date.')}
        </p>
        <div className="mt-4 flex items-center gap-3">
          <Link
            href="/papers"
            className="bg-foreground text-background hover:bg-foreground/85 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors"
          >
            {t('Go to Papers')}
          </Link>
          <Link
            href="/briefing"
            className="border-line hover:bg-line-soft/60 rounded-sm border px-3 py-1.5 text-sm font-medium transition-colors"
          >
            {t('Go to Briefings')}
          </Link>
        </div>
      </Card>
    </div>
  )
}

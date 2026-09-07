'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

export default function BriefingArchiveError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  const t = useT()
  return (
    <RouteError
      error={error}
      retry={retry}
      scope="briefing-archive"
      heading={t("Couldn't load Briefings.")}
      description={t('Nothing was lost. Try again in a moment.')}
      back={{ href: '/dashboard', label: t('Back to Today') }}
    />
  )
}

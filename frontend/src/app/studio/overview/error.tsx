'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

export default function StudioOverviewError({
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
      scope="studio-overview"
      heading={t("Couldn't load this page.")}
      description={t('Nothing was lost. Try again in a moment.')}
      back={{ href: '/studio/runs', label: 'Back to Runs' }}
    />
  )
}

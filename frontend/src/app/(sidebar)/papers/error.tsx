'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

export default function PapersError({
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
      scope="papers"
      heading={t("Couldn't load papers.")}
      description={t('Nothing was lost. Try again in a moment.')}
      back={{ href: '/dashboard', label: t('Back to Today') }}
    />
  )
}

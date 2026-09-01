'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

export default function SettingsError({
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
      scope="settings"
      heading={t("Couldn't load Settings.")}
      description={t('No changes were saved. Try again in a moment.')}
      back={{ href: '/dashboard', label: t('Back to Today') }}
    />
  )
}

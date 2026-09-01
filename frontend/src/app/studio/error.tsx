'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

/**
 * Boundary for the Studio subtree. `forPage` redirects on a 401 and rethrows
 * everything else, so a backend failure lands here rather than on Next's
 * default error screen. Studio content is English-only by decision, but the
 * boundary strings ride the shared chrome dictionary, which is translated.
 */
export default function StudioError({
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
      scope="studio"
      heading={t("Couldn't load this page.")}
      description={t('Nothing was lost. Try again in a moment.')}
      back={{ href: '/dashboard', label: t('Back to Today') }}
    />
  )
}

'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

/**
 * Boundary for the whole authed route group. `forPage` redirects on a 401 and
 * rethrows everything else, so anything the backend fails on lands here rather
 * than on Next's default error screen. More specific boundaries (papers,
 * papers/[id], ask, settings, briefing) sit below with copy that names its
 * object.
 */
export default function SidebarError({
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
      scope="sidebar"
      heading={t("Couldn't load this page.")}
      description={t('Nothing was lost. Try again, or go back to Today.')}
      back={{ href: '/dashboard', label: t('Back to Today') }}
    />
  )
}

'use client'

import { RouteError } from '@/components/route-error'
import { useT } from '@/lib/i18n-client'

export default function PaperDetailError({
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
      scope="paper"
      heading={t("Couldn't load this paper.")}
      description={t('The paper is still there. Try again, or go back to the list.')}
      back={{ href: '/papers', label: t('Back to Papers') }}
    />
  )
}

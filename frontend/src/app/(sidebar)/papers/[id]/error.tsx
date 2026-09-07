'use client'

import { RouteError } from '@/components/route-error'
import { useFeatures } from '@/lib/features-client'
import { useT } from '@/lib/i18n-client'

export default function PaperDetailError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  const t = useT()
  const features = useFeatures()
  // With the list hidden there is no "back to the list": the copy stops naming
  // one and the exit points at Briefings, matching the paper's own nav row.
  return (
    <RouteError
      error={error}
      retry={retry}
      scope="paper"
      heading={t("Couldn't load this paper.")}
      description={
        features.all_papers
          ? t('The paper is still there. Try again, or go back to the list.')
          : t('Nothing was lost. Try again in a moment.')
      }
      back={
        features.all_papers
          ? { href: '/papers', label: t('Back to Papers') }
          : { href: '/briefing', label: t('Go to Briefings') }
      }
    />
  )
}

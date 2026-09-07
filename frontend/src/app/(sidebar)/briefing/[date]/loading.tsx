import { getFeatures } from '@/lib/features-server'
import { getLang, getT } from '@/lib/i18n-server'
import { EditionPageSkeleton } from './skeletons'

/**
 * Instant loading state for an edition, matching the page's own Suspense
 * fallbacks. loading.tsx gets no params, so the date crumb is a bone here.
 */
export default async function Loading() {
  const [t, lang, features] = await Promise.all([getT(), getLang(), getFeatures()])
  return <EditionPageSkeleton t={t} lang={lang} features={features} />
}

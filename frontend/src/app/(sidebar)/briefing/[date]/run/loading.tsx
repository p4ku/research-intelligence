import { getLang, getT } from '@/lib/i18n-server'
import { ScreeningLogPageSkeleton } from './skeletons'

/**
 * Instant loading state for the screening log, matching the page's own
 * Suspense fallback. loading.tsx gets no params, so the date crumb is a bone.
 */
export default async function Loading() {
  const [t, lang] = await Promise.all([getT(), getLang()])
  return <ScreeningLogPageSkeleton t={t} lang={lang} />
}

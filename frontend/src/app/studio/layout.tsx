import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
import { DEFAULT_FEATURES } from '@/lib/features'
import { FeaturesProvider } from '@/lib/features-client'
import { getFeatures } from '@/lib/features-server'
import { getLang } from '@/lib/i18n-server'
import { redirect } from 'next/navigation'

/**
 * The Studio: the operator surface for whoever configures and reviews the
 * pipeline. It shares the reading app's chrome — same account menu — but has
 * its own nav, so the two audiences never see each other's controls. The nav
 * itself lives in the shell (a client module), because icon components
 * cannot cross the server/client boundary.
 */
export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  const user = await getSessionUser()
  // Past the proxy's refresh gate with no resolvable user: the session
  // is unusable, not absent — say so on the login page.
  if (!user) redirect('/?reason=expired')

  const [lang, features] = await Promise.all([getLang(), getFeatures()])
  return (
    <ApplicationLayout lang={lang} features={features} user={user} area="studio">
      {/* Everything Studio renders is pinned to the shipped defaults by this
          nested provider: the skeleton gallery must show the product's shapes
          whatever the demo cookie says, and skeleton:drift must never measure
          a cookie. Nested context wins for the subtree. (The account menu
          shows the switches for any flag the registry has not fixed.) */}
      <FeaturesProvider features={DEFAULT_FEATURES}>{children}</FeaturesProvider>
    </ApplicationLayout>
  )
}

import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
import { emptyStars } from '@/lib/bff/stars/schema'
import { stars } from '@/lib/bff/stars/service'
import { getFeatures } from '@/lib/features-server'
import { getLang } from '@/lib/i18n-server'
import { StarsProvider } from '@/lib/stars-client'
import { redirect } from 'next/navigation'

export default async function SidebarRootLayout({ children }: { children: React.ReactNode }) {
  // The proxy has already gated on the refresh cookie and refreshed the
  // access token; this resolves who is signed in for the chrome. Django
  // validates the token itself on every data call — the shell makes none:
  // the pages read the user's domains themselves (src/lib/workspace-server.ts).
  const user = await getSessionUser()
  // Past the proxy's refresh gate with no resolvable user: the session
  // is unusable, not absent — say so on the login page.
  if (!user) redirect('/?reason=expired')

  // Flags first: a cookie read, no I/O. Then the user's stars seed the client
  // store once per shell render; a failure to read them is "nothing starred",
  // never a broken shell, and with stars hidden the read is skipped outright
  // (the module constant, so StarsProvider's reference re-seed stays stable).
  const features = await getFeatures()
  const [lang, starred] = await Promise.all([
    getLang(),
    features.stars ? stars.get().catch(() => emptyStars) : Promise.resolve(emptyStars),
  ])
  return (
    <ApplicationLayout lang={lang} features={features} user={user}>
      <StarsProvider initial={starred}>{children}</StarsProvider>
    </ApplicationLayout>
  )
}

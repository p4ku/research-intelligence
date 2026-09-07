import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
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

  const lang = await getLang()
  return (
    <ApplicationLayout lang={lang} user={user} area="studio">
      {children}
    </ApplicationLayout>
  )
}

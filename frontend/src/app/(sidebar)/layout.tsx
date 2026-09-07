import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
import { getLang } from '@/lib/i18n-server'
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

  const lang = await getLang()
  return (
    <ApplicationLayout lang={lang} user={user}>
      {children}
    </ApplicationLayout>
  )
}

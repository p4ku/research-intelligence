import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
import { forPage } from '@/lib/bff/core/page'
import { getLang } from '@/lib/i18n-server'
import { getCurrentWorkspace, listWorkspaceChoices } from '@/lib/workspace-server'
import { redirect } from 'next/navigation'

export default async function SidebarRootLayout({ children }: { children: React.ReactNode }) {
  // The proxy has already gated on the refresh cookie and refreshed the
  // access token; this resolves who is signed in for the chrome. Django
  // validates the token itself on every data call.
  const user = await getSessionUser()
  // Past the proxy's refresh gate with no resolvable user: the session
  // is unusable, not absent — say so on the login page.
  if (!user) redirect('/?reason=expired')

  // forPage: a 401 (Django rejected the session) becomes the logout redirect
  // instead of an uncatchable layout throw — error.tsx cannot catch its own
  // layout, so anything escaping here would land on global-error.tsx.
  const [lang, workspaces, current] = await forPage(
    Promise.all([getLang(), listWorkspaceChoices(), getCurrentWorkspace()]),
  )
  return (
    <ApplicationLayout
      lang={lang}
      user={user}
      workspaces={workspaces}
      currentWorkspaceId={current?.id ?? null}
    >
      {children}
    </ApplicationLayout>
  )
}

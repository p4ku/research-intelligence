import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
import { forPage } from '@/lib/bff/core/page'
import { getLang } from '@/lib/i18n-server'
import { getCurrentWorkspace, listWorkspaceChoices } from '@/lib/workspace-server'
import { redirect } from 'next/navigation'

/**
 * The Studio: the operator surface for whoever configures and reviews the
 * pipeline. It shares the reading app's chrome — same workspace switcher, same
 * account menu — but has its own nav, so the two audiences never see each
 * other's controls. The nav itself lives in the shell (a client module),
 * because icon components cannot cross the server/client boundary.
 */
export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  const user = await getSessionUser()
  if (!user) redirect('/')

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
      area="studio"
    >
      {children}
    </ApplicationLayout>
  )
}

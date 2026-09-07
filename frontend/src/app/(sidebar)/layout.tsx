import { ApplicationLayout } from '@/components/application-layout'
import { getSessionUser } from '@/lib/auth/session'
import { ProblemError } from '@/lib/bff/core/problem'
import { emptyStars, type Stars } from '@/lib/bff/stars/schema'
import { stars } from '@/lib/bff/stars/service'
import { getLang } from '@/lib/i18n-server'
import { StarsProvider } from '@/lib/stars-client'
import { redirect } from 'next/navigation'

/**
 * The user's stars, or nothing starred when they cannot be read. A 401 is
 * the session ending (the `forPage` rule), never "nothing starred"; any
 * other failure is logged, since a broken shell would be worse than an
 * unstarred one. With the cookie stub this is a cookie read; once the
 * resource is on Django it is one round trip per shell render.
 */
async function readStars(): Promise<Stars> {
  try {
    return await stars.get()
  } catch (error) {
    if (error instanceof ProblemError && error.problem.status === 401) {
      redirect('/auth/logout?reason=expired')
    }
    console.error('[stars] unreadable; rendering nothing starred', error)
    return emptyStars
  }
}

export default async function SidebarRootLayout({ children }: { children: React.ReactNode }) {
  // The proxy has already gated on the refresh cookie and refreshed the
  // access token; this resolves who is signed in for the chrome. Django
  // validates the token itself on every data call — the shell makes none:
  // the pages read the user's domains themselves (src/lib/workspace-server.ts).
  const user = await getSessionUser()
  // Past the proxy's refresh gate with no resolvable user: the session
  // is unusable, not absent — say so on the login page.
  if (!user) redirect('/?reason=expired')

  // The user's stars seed the client store once per shell render.
  const [lang, starred] = await Promise.all([getLang(), readStars()])
  return (
    <ApplicationLayout lang={lang} user={user}>
      <StarsProvider initial={starred}>{children}</StarsProvider>
    </ApplicationLayout>
  )
}

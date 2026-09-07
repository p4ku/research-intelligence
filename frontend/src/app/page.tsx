import { hasSessionCookies } from '@/lib/auth/session'
import { makeT } from '@/lib/i18n'
import { getLang } from '@/lib/i18n-server'
import { redirect } from 'next/navigation'
import { LoginPanel } from './login-panel'

export const dynamic = 'force-dynamic'

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; reason?: string }>
}) {
  // Cookie presence only; if the tokens are stale the proxy clears them on
  // the way into /dashboard and sends the user back here.
  if (await hasSessionCookies()) redirect('/dashboard')
  const [{ next, reason }, lang] = await Promise.all([searchParams, getLang()])
  const t = makeT(lang)

  return (
    <main className="grid min-h-dvh lg:grid-cols-2">
      {/* Login */}
      <div className="flex items-center justify-center bg-surface px-6 py-16">
        <LoginPanel
          next={next}
          lang={lang}
          notice={
            reason === 'expired'
              ? t('Your session expired. Please sign in again.')
              : reason === 'signed-out'
                ? t('You have been signed out.')
                : undefined
          }
        />
      </div>

      {/* Branded scan panel — schwarz surface */}
      <div className="relative hidden overflow-hidden bg-[#0b0b0a] lg:block">
        <ScanField />
      </div>
    </main>
  )
}

// A faint concentric "scanner" backdrop rendered as inline SVG.
function ScanField() {
  const rings = [80, 150, 220, 290, 360, 430]
  return (
    <svg
      className="absolute inset-0 h-full w-full"
      viewBox="0 0 600 800"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="scan-fade" cx="50%" cy="42%" r="60%">
          <stop offset="0%" stopColor="#00c3cd" stopOpacity="0.28" />
          <stop offset="60%" stopColor="#00c3cd" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#00c3cd" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="600" height="800" fill="url(#scan-fade)" />
      {rings.map((r) => (
        <circle
          key={r}
          cx="300"
          cy="340"
          r={r}
          fill="none"
          stroke="#ffffff"
          strokeOpacity={0.06}
          strokeWidth="1"
        />
      ))}
      {/* a few plotted "signals" on the field */}
      {[
        [300, 340, 5],
        [372, 300, 3],
        [250, 250, 2.5],
        [430, 420, 3.5],
        [200, 430, 2],
        [360, 480, 2.5],
        [470, 300, 2],
      ].map(([cx, cy, r], i) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill="#00c3cd" fillOpacity={0.85} />
      ))}
    </svg>
  )
}

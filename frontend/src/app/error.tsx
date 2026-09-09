'use client'

import { fmt, LANG_COOKIE, makeT, type Lang } from '@/lib/i18n'
import Link from 'next/link'
import { useEffect, useSyncExternalStore } from 'react'

/** The UI language straight off the cookie: this boundary sits above the
 *  LanguageProvider (the sign-in page has no app shell), so there is no
 *  context to read. */
function readLang(): Lang {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${LANG_COOKIE}=([^;]*)`))
  return match?.[1] === 'de' ? 'de' : 'en'
}

// The cookie cannot change while this card is on screen, so there is nothing
// to subscribe to; useSyncExternalStore is here for its server snapshot, which
// is what lets a client-only read cross hydration without a mismatch.
const noSubscribe = () => () => {}
const serverLang = (): Lang => 'en'

/**
 * Root-segment boundary: catches a failure on the sign-in page itself. Below
 * the root layout, so the stylesheet and fonts are available; above every
 * provider, so the language comes from the cookie and t() is built by hand.
 */
export default function RootError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  const t = makeT(useSyncExternalStore(noSubscribe, readLang, serverLang))

  useEffect(() => {
    console.error('[boundary:root]', error.digest ?? '', error)
  }, [error])

  return (
    <main className="grid min-h-dvh place-items-center bg-background text-foreground">
      <div role="alert" className="m-4 max-w-md rounded-sm border border-line bg-surface px-6 py-5">
        <p className="text-sm font-medium">{t('Something went wrong loading this page.')}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t('Nothing was lost. Try again in a moment.')}
        </p>
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => retry()}
            className="rounded-sm bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
          >
            {t('Retry')}
          </button>
          <Link
            href="/"
            className="rounded-sm border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:bg-line-soft/60"
          >
            {t('Back to sign-in')}
          </Link>
        </div>
        {error.digest && (
          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            {fmt(t('Reference {id}'), { id: error.digest })}
          </p>
        )}
      </div>
    </main>
  )
}

'use client'

import { useEffect, useSyncExternalStore } from 'react'

/**
 * The only boundary above the root layout: it must render its own
 * <html>/<body> and deliberately imports nothing shared — this surface
 * appears precisely when providers or the root layout are what failed. That
 * includes the dictionary and `LANG_COOKIE`: the cookie name and both
 * sentences are inlined below rather than imported. Only exercised in
 * production builds — verify with `bun run build && bun run start`, not `dev`.
 */

/** Same cookie the rest of the app reads, spelled out (see above). */
const LANG_COOKIE = 'rs-lang'

const COPY = {
  de: {
    title: 'Diese Seite konnte nicht geladen werden.',
    body: 'Ihre Daten sind nicht betroffen.',
    retry: 'Erneut versuchen',
    back: 'Zurück zur Startseite',
    reference: 'Referenz',
  },
  en: {
    title: "Couldn't load this page.",
    body: 'Your data is unaffected.',
    retry: 'Retry',
    back: 'Back to Home',
    reference: 'Reference',
  },
} as const

function readLang(): 'en' | 'de' {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${LANG_COOKIE}=([^;]*)`))
  return match?.[1] === 'de' ? 'de' : 'en'
}

// Nothing to subscribe to — the cookie cannot change while this card is up.
// English is the default here exactly as it is in src/app/error.tsx and
// makeT: German is what an explicit `rs-lang=de` cookie asks for, and a
// boundary that fires before the cookie is read must not guess otherwise.
const noSubscribe = () => () => {}
const serverLang = (): 'en' | 'de' => 'en'

export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  const lang = useSyncExternalStore(noSubscribe, readLang, serverLang)
  const copy = COPY[lang]

  useEffect(() => {
    console.error('[boundary:global]', error.digest ?? '', error)
  }, [error])

  return (
    <html lang={lang}>
      <body
        style={{
          margin: 0,
          background: '#f3f4f4',
          color: '#131311',
          fontFamily: 'system-ui, sans-serif',
          minHeight: '100dvh',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        <main
          style={{
            background: '#ffffff',
            border: '1px solid #deded7',
            borderRadius: 2,
            padding: '20px 24px',
            maxWidth: 420,
            margin: 16,
          }}
        >
          <p style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{copy.title}</p>
          <p style={{ margin: '6px 0 0', fontSize: 14, color: '#6d6d65' }}>{copy.body}</p>
          <div style={{ marginTop: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => (typeof retry === 'function' ? retry() : window.location.reload())}
              style={{
                background: '#131311',
                color: '#ffffff',
                border: 0,
                borderRadius: 2,
                padding: '6px 12px',
                fontSize: 14,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              {copy.retry}
            </button>
            <a href="/dashboard" style={{ color: '#131311', fontSize: 14 }}>
              {copy.back}
            </a>
          </div>
          {error.digest && (
            <p
              style={{
                margin: '12px 0 0',
                fontFamily: 'ui-monospace, monospace',
                fontSize: 11,
                color: '#6d6d65',
              }}
            >
              {copy.reference} {error.digest}
            </p>
          )}
        </main>
      </body>
    </html>
  )
}

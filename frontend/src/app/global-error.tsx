'use client'

import { useEffect } from 'react'

/**
 * The only boundary above the root layout: it must render its own
 * <html>/<body> and deliberately imports nothing shared — this surface
 * appears precisely when providers or the root layout are what failed.
 * German is hardcoded (the deployment's language); the language cookie and
 * provider are unavailable here by design. Only exercised in production
 * builds — verify with `bun run build && bun run start`, not `dev`.
 */
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  useEffect(() => {
    console.error('[boundary:global]', error.digest ?? '', error)
  }, [error])

  return (
    <html lang="de">
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
          <p style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
            Diese Seite konnte nicht geladen werden.
          </p>
          <p style={{ margin: '6px 0 0', fontSize: 14, color: '#6d6d65' }}>
            Ihre Daten sind nicht betroffen.
          </p>
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
              Erneut versuchen
            </button>
            <a href="/dashboard" style={{ color: '#131311', fontSize: 14 }}>
              Zurück zu Heute
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
              Referenz {error.digest}
            </p>
          )}
        </main>
      </body>
    </html>
  )
}

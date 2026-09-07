'use client'

import Link from 'next/link'
import { useEffect } from 'react'

/**
 * Root-segment boundary: catches a failure on the sign-in page itself.
 * English, matching the (deliberately) English-only login panel. Below the
 * root layout, so the stylesheet and fonts are available.
 */
export default function RootError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  useEffect(() => {
    console.error('[boundary:root]', error.digest ?? '', error)
  }, [error])

  return (
    <main className="grid min-h-dvh place-items-center bg-background text-foreground">
      <div role="alert" className="m-4 max-w-md rounded-sm border border-line bg-surface px-6 py-5">
        <p className="text-sm font-medium">Something went wrong loading this page.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Nothing was lost. Try again in a moment.
        </p>
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => retry()}
            className="rounded-sm bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-colors hover:bg-foreground/85"
          >
            Retry
          </button>
          <Link
            href="/"
            className="rounded-sm border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:bg-line-soft/60"
          >
            Back to sign-in
          </Link>
        </div>
        {error.digest && (
          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            Reference {error.digest}
          </p>
        )}
      </div>
    </main>
  )
}

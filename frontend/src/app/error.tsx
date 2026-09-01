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
    <main className="bg-background text-foreground grid min-h-dvh place-items-center">
      <div role="alert" className="bg-surface border-line m-4 max-w-md rounded-sm border px-6 py-5">
        <p className="text-sm font-medium">Something went wrong loading this page.</p>
        <p className="text-muted-foreground mt-1 text-sm">Nothing was lost. Try again in a moment.</p>
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => retry()}
            className="bg-foreground text-background hover:bg-foreground/85 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors"
          >
            Retry
          </button>
          <Link
            href="/"
            className="border-line hover:bg-line-soft/60 rounded-sm border px-3 py-1.5 text-sm font-medium transition-colors"
          >
            Back to sign-in
          </Link>
        </div>
        {error.digest && (
          <p className="text-muted-foreground mt-3 font-mono text-[11px]">Reference {error.digest}</p>
        )}
      </div>
    </main>
  )
}

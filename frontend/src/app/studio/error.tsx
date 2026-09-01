'use client'

import { Card } from '@/components/scanner-ui'

/**
 * Boundary for the Studio subtree. `forPage` redirects on a 401 and rethrows
 * everything else, so a backend failure lands here rather than on Next's
 * default error screen.
 */
export default function StudioError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <Card>
      <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
        Something went wrong loading this page.
      </p>
      <p className="mt-1 font-mono text-xs text-zinc-500 dark:text-zinc-400">{error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded-md bg-zinc-950 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
      >
        Retry
      </button>
    </Card>
  )
}

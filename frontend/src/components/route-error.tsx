'use client'

import { Card } from '@/components/scanner-ui'
import { Spinner } from '@/components/ui/spinner'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { ExclamationTriangleIcon } from '@heroicons/react/16/solid'
import { useEffect, useTransition } from 'react'

/**
 * Shared fallback for route error boundaries (`error.tsx` files). Renders
 * product copy — never `error.message`, which in production is Next's generic
 * Server-Components placeholder — plus `error.digest` as a support reference
 * and a Retry wired to Next 16.3's `retry()`, which re-fetches the segment
 * (`reset()` only re-rendered the cached tree, so it could never recover a
 * Server Component failure).
 */
export function RouteError({
  error,
  retry,
  scope,
  heading,
  description,
  back,
}: {
  error: Error & { digest?: string }
  retry: () => void
  /** Stable tag for logs, e.g. 'papers'. */
  scope: string
  heading: string
  description: string
  back: { href: string; label: string }
}) {
  const t = useT()
  const [retrying, startRetry] = useTransition()

  useEffect(() => {
    // The one reporting seam: swap in a real error reporter here later.
    console.error(`[boundary:${scope}]`, error.digest ?? '', error)
  }, [error, scope])

  return (
    <Card role="alert">
      <div className="flex items-start gap-2.5">
        <ExclamationTriangleIcon
          aria-hidden="true"
          className="text-negative mt-0.5 size-4 shrink-0"
        />
        <div className="min-w-0">
          <p className="text-foreground text-sm font-medium">{heading}</p>
          <p className="text-muted-foreground mt-1 text-sm">{description}</p>
          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={() => startRetry(() => retry())}
              disabled={retrying}
              className="bg-foreground text-background hover:bg-foreground/85 inline-flex items-center gap-2 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-60"
            >
              {retrying && <Spinner className="size-3.5" aria-hidden="true" />}
              {retrying ? t('Retrying…') : t('Retry')}
            </button>
            {/* Plain <a>: a full navigation is the sturdiest escape from a broken tree. */}
            <a
              href={back.href}
              className="border-line hover:bg-line-soft/60 rounded-sm border px-3 py-1.5 text-sm font-medium transition-colors"
            >
              {back.label}
            </a>
          </div>
          {error.digest && (
            <p className="text-muted-foreground mt-3 font-mono text-[11px]">
              {fmt(t('Reference {id}'), { id: error.digest })}
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}

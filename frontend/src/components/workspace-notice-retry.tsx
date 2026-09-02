'use client'

import { Spinner } from '@/components/ui/spinner'
import { useRouter } from 'next/navigation'
import { useTransition } from 'react'

/** Retry for a server-rendered notice: re-runs the page's fetches in place. */
export function RefreshButton({ label, busyLabel }: { label: string; busyLabel: string }) {
  const router = useRouter()
  const [retrying, startRetry] = useTransition()

  return (
    <button
      type="button"
      onClick={() => startRetry(() => router.refresh())}
      disabled={retrying}
      className="bg-foreground text-background hover:bg-foreground/85 inline-flex items-center gap-2 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-60"
    >
      {retrying && <Spinner className="size-3.5" aria-hidden="true" />}
      {retrying ? busyLabel : label}
    </button>
  )
}

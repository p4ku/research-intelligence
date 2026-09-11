'use client'

import { sessionExpired } from '@/lib/auth/leave'
import { problemBody, type Problem } from '@/lib/bff/core/problem'
import { problemMessage } from '@/lib/bff/problem-copy'
import { useT } from '@/lib/i18n-client'
import { ArrowDownTrayIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { Loader2Icon } from 'lucide-react'
import { useState, type MouseEvent } from 'react'
import { toast } from 'sonner'

/**
 * The screening log's export: a link to the BFF's PDF that saves in place.
 * Without JavaScript it is that link (the response is an attachment); with
 * it, the click fetches the file so the button can show it is working and
 * a failure is a toast in the reader's language, not a bare problem page.
 */
export function ExportPdfButton({ href }: { href: string }) {
  const t = useT()
  const [busy, setBusy] = useState(false)

  async function download(e: MouseEvent<HTMLAnchorElement>) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      const res = await fetch(href)
      if (!res.ok) {
        const isProblem = res.headers.get('content-type')?.includes('application/problem+json')
        const problem = isProblem
          ? ((await res.json()) as Problem)
          : problemBody('upstream-unavailable', { instance: href })
        if (problem.status === 401) return sessionExpired()
        toast.error(problemMessage(problem, t))
        return
      }
      const blob = await res.blob()
      saveFile(blob, filenameOf(res.headers.get('content-disposition')) ?? 'screening-log.pdf')
    } catch {
      toast.error(problemMessage(problemBody('upstream-unavailable', { instance: href }), t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <a
      href={href}
      download
      onClick={download}
      aria-busy={busy || undefined}
      title={busy ? t('Preparing the PDF') : undefined}
      className={clsx(
        'group inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-[13px]/none font-medium transition-colors',
        'border-zinc-950/10 bg-white text-zinc-600 shadow-xs hover:border-zinc-950/15 hover:text-zinc-950',
        'dark:border-white/10 dark:bg-white/5 dark:text-zinc-300 dark:shadow-none dark:hover:border-white/20 dark:hover:text-white',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500',
        busy && 'cursor-progress',
      )}
    >
      {busy ? (
        <Loader2Icon aria-hidden="true" className="size-3.5 animate-spin text-zinc-400" />
      ) : (
        <ArrowDownTrayIcon
          aria-hidden="true"
          className="size-3.5 text-zinc-400 transition-colors group-hover:text-zinc-600 dark:text-zinc-500 dark:group-hover:text-zinc-300"
        />
      )}
      {t('Export PDF')}
      {busy && <span className="sr-only">{t('Preparing the PDF')}</span>}
    </a>
  )
}

function filenameOf(disposition: string | null): string | null {
  const match = disposition?.match(/filename="([^"]+)"/)
  return match ? match[1] : null
}

function saveFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  // The click has taken the URL by the time this runs.
  setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

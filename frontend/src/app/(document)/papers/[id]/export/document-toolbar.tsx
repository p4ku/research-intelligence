'use client'

import { useT } from '@/lib/i18n-client'
import { ArrowDownTrayIcon, ChevronLeftIcon } from '@heroicons/react/16/solid'
import { useEffect } from 'react'

/**
 * The bar above the sheet, on screen only (document.css hides it in print):
 * the way back to the paper, one line on what this view is, and the button
 * that re-opens the print dialog for a reader who dismissed it.
 *
 * The dialog opens by itself once the fonts are in, so the tab the export
 * link opens goes straight to "Save as PDF". The effect waits on
 * `document.fonts.ready` and a frame of layout, and its cleanup cancels the
 * pending call — under StrictMode's mount / unmount / mount the first pass
 * is cancelled and the second one prints, once.
 */
export function DocumentToolbar({ backHref }: { backHref: string }) {
  const t = useT()

  useEffect(() => {
    let cancelled = false
    const ready = typeof document.fonts?.ready?.then === 'function' ? document.fonts.ready : null
    const print = () => {
      if (cancelled) return
      requestAnimationFrame(() => {
        if (!cancelled) window.print()
      })
    }
    if (ready) ready.then(print, print)
    else print()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="doc-toolbar" data-shape="document-toolbar">
      <a href={backHref} className="doc-toolbar-back">
        <ChevronLeftIcon aria-hidden="true" className="size-4" />
        {t('Back to paper')}
      </a>
      <p className="doc-toolbar-hint">
        {t('Laid out for A4. In the print dialog, choose “Save as PDF”.')}
      </p>
      <button type="button" onClick={() => window.print()} className="doc-toolbar-print">
        <ArrowDownTrayIcon aria-hidden="true" className="size-3.5" />
        {t('Save as PDF')}
      </button>
    </div>
  )
}

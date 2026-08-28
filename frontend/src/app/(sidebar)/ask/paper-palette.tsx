'use client'

import { SignalScore } from '@/components/scanner-ui'
import { fmt, formatDate } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import * as Headless from '@headlessui/react'
import { CheckIcon, MagnifyingGlassIcon } from '@heroicons/react/16/solid'
import { useState } from 'react'
import type { PaletteEntry } from './types'

function matches(entry: PaletteEntry, query: string): boolean {
  const q = query.toLowerCase()
  return (
    entry.title.toLowerCase().includes(q) ||
    (entry.first_author?.toLowerCase().includes(q) ?? false) ||
    entry.source.toLowerCase().includes(q) ||
    entry.id.includes(q)
  )
}

/**
 * Command-palette paper picker over the workspace corpus (score-first rows;
 * entries arrive pre-sorted by signal).
 */
export function PaperPalette({
  open,
  entries,
  currentPaperId,
  onClose,
  onSelect,
}: {
  open: boolean
  entries: PaletteEntry[]
  currentPaperId?: string
  onClose: () => void
  onSelect: (entry: PaletteEntry) => void
}) {
  const t = useT()
  const [query, setQuery] = useState('')

  const shown = query.trim() ? entries.filter((e) => matches(e, query.trim())) : entries

  function close() {
    onClose()
    setQuery('')
  }

  return (
    <Headless.Dialog open={open} onClose={close} className="relative z-50">
      <Headless.DialogBackdrop
        transition
        className="fixed inset-0 bg-zinc-950/25 transition duration-150 ease-out data-closed:opacity-0 motion-reduce:transition-none dark:bg-zinc-950/50"
      />
      <div className="fixed inset-0 flex items-start justify-center overflow-y-auto p-4 pt-[10vh] sm:pt-[15vh]">
        <Headless.DialogPanel
          transition
          className="w-full max-w-xl overflow-hidden rounded-xl border border-zinc-950/10 bg-white shadow-2xl transition duration-150 ease-out data-closed:scale-[0.98] data-closed:opacity-0 motion-reduce:transition-none dark:border-white/10 dark:bg-zinc-900"
        >
          <Headless.Combobox<PaletteEntry | null>
            value={null}
            onChange={(entry) => {
              if (entry) {
                onSelect(entry)
                close()
              }
            }}
          >
            <div className="flex items-center gap-2.5 border-b border-zinc-950/8 px-4 dark:border-white/10">
              <MagnifyingGlassIcon className="size-4 shrink-0 text-zinc-400" />
              <Headless.ComboboxInput
                autoFocus
                placeholder={t('Find a paper — title, author, source…')}
                aria-label={t('Find a paper to scope the conversation to')}
                onChange={(e) => setQuery(e.target.value)}
                className="min-w-0 flex-1 bg-transparent py-3.5 text-sm text-zinc-900 placeholder:text-zinc-500 focus:outline-none dark:text-zinc-100 dark:placeholder:text-zinc-400"
              />
              <kbd className="hidden rounded-sm border border-zinc-950/10 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400 sm:block dark:border-white/15">
                esc
              </kbd>
            </div>

            <Headless.ComboboxOptions static className="max-h-[24rem] overflow-y-auto p-1.5">
              {shown.length > 0 ? (
                shown.map((entry) => (
                  <PaperOption
                    key={entry.id}
                    entry={entry}
                    current={entry.id === currentPaperId}
                  />
                ))
              ) : (
                <p className="px-3 py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
                  {fmt(t('No papers match “{q}” — the workspace holds {n} papers.'), {
                    q: query.trim(),
                    n: entries.length,
                  })}
                </p>
              )}
            </Headless.ComboboxOptions>

            <div className="flex items-center gap-3 border-t border-zinc-950/8 px-4 py-2 text-[11px] text-zinc-400 dark:border-white/10 dark:text-zinc-500">
              <span>
                <kbd className="font-mono">↑↓</kbd> {t('navigate')}
              </span>
              <span>
                <kbd className="font-mono">↵</kbd> {t('scope the conversation')}
              </span>
              <span className="ml-auto tabular-nums">
                {fmt(t('{n} papers scanned'), { n: entries.length })}
              </span>
            </div>
          </Headless.Combobox>
        </Headless.DialogPanel>
      </div>
    </Headless.Dialog>
  )
}

function PaperOption({ entry, current }: { entry: PaletteEntry; current: boolean }) {
  const { lang } = useLanguage()
  return (
    <Headless.ComboboxOption
      value={entry}
      className="group flex cursor-default items-center gap-3 rounded-lg px-2.5 py-2 data-focus:bg-zinc-950/5 dark:data-focus:bg-white/10"
    >
      <SignalScore score={entry.signal_score} size="sm" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {entry.title}
        </div>
        <div className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
          {[entry.first_author, entry.source, formatDate(entry.created_at, lang)]
            .filter(Boolean)
            .join(' · ')}
        </div>
      </div>
      {current && <CheckIcon className="size-4 shrink-0 text-blue-600 dark:text-blue-400" />}
    </Headless.ComboboxOption>
  )
}

'use client'

import { useT } from '@/lib/i18n-client'
import { MagnifyingGlassIcon } from '@heroicons/react/16/solid'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

/**
 * The spec's one plain-language field: every paper by topic, technology,
 * title or author. Submitting opens Papers with the query; an empty search
 * opens Papers showing everything. No query syntax — Papers matches the
 * words against titles, abstracts and authors.
 */
export function SearchField() {
  const t = useT()
  const router = useRouter()
  const [q, setQ] = useState('')
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault()
        const query = q.trim()
        router.push(query ? `/papers?q=${encodeURIComponent(query)}` : '/papers')
      }}
      className="group relative flex items-center gap-3 rounded-md border border-line bg-surface px-4 py-3 transition focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent/15"
    >
      <MagnifyingGlassIcon className="size-5 shrink-0 text-zinc-400 transition-colors group-focus-within:text-accent" />
      <input
        name="q"
        type="search"
        aria-label={t('Search papers')}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t('Search papers by topic, technology, title or author')}
        className="min-w-0 flex-1 bg-transparent text-base text-zinc-950 placeholder:text-zinc-400 focus:outline-none dark:text-white [&::-webkit-search-cancel-button]:hidden"
      />
    </form>
  )
}

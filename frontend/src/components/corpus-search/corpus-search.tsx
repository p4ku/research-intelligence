'use client'

import { SearchFrame } from '@/components/search-frame'
import { Spinner } from '@/components/ui/spinner'
import { bffFetch } from '@/lib/bff/client'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { tokenize } from '@/lib/search/match'
import { XMarkIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useRouter } from 'next/navigation'
import {
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  useTransition,
  type KeyboardEvent,
} from 'react'
import { HANDLED_KEYS, reduceKey } from './keys'
import { SearchPanel } from './panel'
import { clearRecent, pushRecent, readRecent } from './recent'
import { buildSections, flatten, papersHref, rowHref, rowId, type Row } from './rows'
import { searchPath, useSearch } from './use-search'

/** How long a fetch may take before the magnifier turns into a spinner. */
const SLOW_MS = 200
/** How long a row must stay highlighted before its route is prefetched. */
const PREFETCH_MS = 100

/**
 * The corpus search: one field, results under it as you type, Enter with
 * nothing highlighted opens Papers with the query. Home mounts it; it holds
 * no page state, so any page could.
 *
 * - Results appear on the second character; the previous request is aborted
 *   on every keystroke and the last good result stays visible, dimmed.
 * - ↑↓ move, Enter opens, Escape closes and then clears, Tab leaves. No
 *   keycaps: the field explains itself by responding.
 * - An arXiv id or DOI shows one "Open paper" row and Enter opens it.
 * - Navigation runs in a transition: the field dims and the magnifier spins
 *   until the next page is ready, and the text never disappears.
 */
export function CorpusSearch({
  domains,
  suggestions = [],
  placeholder,
  limit = 6,
}: {
  /** The user's domains: with more than one, paper rows name theirs. */
  domains: { id: string; name: string }[]
  /** "Try" rows when nothing is typed — the domains' own scan topics. */
  suggestions?: string[]
  placeholder?: string
  limit?: number
}) {
  const t = useT()
  const router = useRouter()
  const panelId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(-1)
  const [recent, setRecent] = useState<string[]>([])
  const [navigating, startNavigation] = useTransition()
  const byKeyboard = useRef(false)
  const warmed = useRef(false)

  const { result, pending, error } = useSearch(q, { limit })
  const deferred = useDeferredValue(result)
  const trimmed = q.trim()
  const fresh = result !== null && result.query === trimmed

  // Recent searches live in the browser: read after mount so the server
  // and first client render agree.
  useEffect(() => {
    // Same reasoning as useStoredOpen in collapsible-section.tsx: reading
    // storage during render would break hydration of the streamed page.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRecent(readRecent())
  }, [])

  const sections = useMemo(
    () => buildSections(deferred, { q, recent, suggestions, error, t }),
    [deferred, q, recent, suggestions, error, t],
  )
  const rows = useMemo(() => flatten(sections), [sections])
  const active = cursor < rows.length ? cursor : -1
  const activeRow: Row | undefined = active >= 0 ? rows[active] : undefined
  const expanded = open && sections.length > 0
  const tokens = useMemo(() => tokenize(trimmed), [trimmed])

  // A slow fetch earns a spinner; a fast one never flickers. The timer
  // records which text was slow, so the spinner is derived, never reset.
  const [slowFor, setSlowFor] = useState<string | null>(null)
  useEffect(() => {
    if (!pending) return
    const timer = setTimeout(() => setSlowFor(trimmed), SLOW_MS)
    return () => clearTimeout(timer)
  }, [pending, trimmed])
  const slow = pending && slowFor === trimmed

  // Keyboard travel keeps the highlighted row in view; the mouse never scrolls.
  useEffect(() => {
    if (!byKeyboard.current || !activeRow) return
    byKeyboard.current = false
    document.getElementById(rowId(activeRow))?.scrollIntoView({ block: 'nearest' })
  }, [activeRow])

  // The highlighted row's destination is warmed so Enter lands at once.
  useEffect(() => {
    const href = activeRow ? rowHref(activeRow) : null
    if (!href) return
    const timer = setTimeout(() => router.prefetch(href), PREFETCH_MS)
    return () => clearTimeout(timer)
  }, [activeRow, router])

  function go(href: string, remember: boolean) {
    if (remember) setRecent(pushRecent(q))
    setOpen(false)
    startNavigation(() => router.push(href))
  }

  function submit() {
    if (!trimmed) return go('/papers', false)
    if (fresh && result.intent === 'id' && result.exact) {
      return go(`/papers/${result.exact.paper_id}`, true)
    }
    go(papersHref(trimmed), true)
  }

  function activate(row: Row) {
    if (row.kind === 'recent' || row.kind === 'try') {
      setQ(row.q)
      setCursor(-1)
      setOpen(true)
      inputRef.current?.focus()
      return
    }
    go(row.href, row.kind !== 'papers')
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.nativeEvent.isComposing) return
    const action = reduceKey(e.key, { open, cursor: active, hasText: q !== '' }, rows.length)
    if (HANDLED_KEYS.has(e.key)) e.preventDefault()
    switch (action.type) {
      case 'open':
        setOpen(true)
        break
      case 'close':
        setOpen(false)
        setCursor(-1)
        break
      case 'clear':
        setQ('')
        setCursor(-1)
        break
      case 'cursor':
        byKeyboard.current = true
        setOpen(true)
        setCursor(action.cursor)
        break
      case 'activate':
        if (activeRow) activate(activeRow)
        break
      case 'submit':
        submit()
        break
      case 'none':
        break
    }
  }

  function onFocus() {
    setOpen(true)
    router.prefetch('/papers')
    if (!warmed.current) {
      // One empty query warms the server's corpus cache so the first real
      // keystroke answers from memory.
      warmed.current = true
      bffFetch(searchPath('', 1)).catch(() => {})
    }
  }

  const status = navigating
    ? t('Opening Papers…')
    : pending
      ? t('Searching…')
      : fresh && result.intent !== 'empty'
        ? fmt(t('{n} hits'), { n: result.papers_total })
        : ''

  return (
    <div
      ref={rootRef}
      className={clsx('relative transition-opacity', navigating && 'opacity-60')}
      data-navigating={navigating || undefined}
      onBlur={(e) => {
        if (!rootRef.current?.contains(e.relatedTarget as Node | null)) {
          setOpen(false)
          setCursor(-1)
        }
      }}
    >
      <SearchFrame
        leading={
          navigating || slow ? (
            <Spinner className="text-accent size-4" aria-label={status} />
          ) : undefined
        }
      >
        <input
          ref={inputRef}
          name="q"
          type="search"
          role="combobox"
          aria-label={t('Search papers')}
          aria-expanded={expanded}
          aria-controls={panelId}
          aria-autocomplete="list"
          aria-activedescendant={activeRow ? rowId(activeRow) : undefined}
          aria-busy={navigating || undefined}
          autoComplete="off"
          spellCheck={false}
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setCursor(-1)
            setOpen(true)
          }}
          onFocus={onFocus}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? t('Search papers by topic, technology, title or author')}
          className="min-w-0 flex-1 bg-transparent text-base text-zinc-950 placeholder:text-zinc-400 focus:outline-none dark:text-white [&::-webkit-search-cancel-button]:hidden"
        />
        {q !== '' && (
          <>
            <span className="min-w-[6ch] shrink-0 text-right font-mono text-xs text-zinc-400 tabular-nums">
              {fresh && result.intent !== 'empty'
                ? fmt(t('{n} hits'), { n: result.papers_total })
                : ''}
            </span>
            <button
              type="button"
              tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                setQ('')
                setCursor(-1)
                inputRef.current?.focus()
              }}
              aria-label={t('Clear search')}
              className="shrink-0 rounded-md p-1 text-zinc-400 hover:bg-zinc-950/5 hover:text-zinc-950 dark:hover:bg-white/10 dark:hover:text-white"
            >
              <XMarkIcon className="size-4" />
            </button>
          </>
        )}
      </SearchFrame>

      <p role="status" aria-live="polite" className="sr-only">
        {status}
      </p>

      {expanded && (
        <SearchPanel
          id={panelId}
          sections={sections}
          cursor={active}
          pending={pending && deferred !== null}
          tokens={tokens}
          showDomain={domains.length > 1}
          onCursor={setCursor}
          onActivate={activate}
          onClearRecent={() => {
            clearRecent()
            setRecent([])
          }}
        />
      )}
    </div>
  )
}

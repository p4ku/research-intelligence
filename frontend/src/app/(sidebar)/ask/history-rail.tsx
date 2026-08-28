'use client'

import { SectionLabel } from '@/components/scanner-ui'
import type { ChatSession } from '@/lib/bff/chat/schema'
import { fmt } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { PlusIcon, TrashIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { shortTitle, timeOf } from './types'

/** 'Today', 'Yesterday', or a short local date — the rail's group label. */
function dayLabel(iso: string, lang: string, t: (s: string) => string): string {
  const date = new Date(iso)
  const today = new Date()
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOf(today) - startOf(date)) / 86_400_000)
  if (days <= 0) return t('Today')
  if (days === 1) return t('Yesterday')
  return date.toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

function HistoryRow({
  session,
  active,
  onOpen,
  onDelete,
}: {
  session: ChatSession
  active: boolean
  onOpen: () => void
  onDelete: () => void
}) {
  const t = useT()
  return (
    <div
      className={clsx(
        'group flex w-full items-stretch gap-2.5 rounded-sm py-2 pr-2 pl-2',
        active ? 'border-line bg-surface border shadow-xs' : 'hover:bg-foreground/5',
      )}
    >
      {/* Scope spine: accent for a single paper, neutral for the whole corpus. */}
      <span
        aria-hidden="true"
        className={clsx(
          'w-[3px] shrink-0 rounded-full',
          session.paper_id ? 'bg-accent/70' : 'bg-line-strong',
        )}
      />
      <button type="button" onClick={onOpen} aria-current={active || undefined} className="min-w-0 flex-1 text-left">
        <span
          className={clsx(
            'line-clamp-2 block text-xs',
            active ? 'text-foreground font-medium' : 'text-muted-foreground',
          )}
        >
          {session.title}
        </span>
        <span className="text-muted-foreground mt-1 flex min-w-0 items-center gap-1.5 font-mono text-[10px] tabular-nums">
          {active && <span className="bg-accent size-1.5 shrink-0 rounded-full" />}
          <span className="shrink-0">{timeOf(session.updated_at)}</span>
          <span aria-hidden="true">·</span>
          {session.paper_title ? (
            <span className="truncate">{shortTitle(session.paper_title)}</span>
          ) : (
            <span className="truncate">{t('All papers')}</span>
          )}
          <span aria-hidden="true">·</span>
          <span className="shrink-0">{fmt(t('{n} turns'), { n: session.turns_count })}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onDelete}
        title={t('Delete conversation')}
        aria-label={t('Delete conversation')}
        className="text-muted-foreground hover:text-foreground self-center rounded-sm p-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
      >
        <TrashIcon className="size-3.5" />
      </button>
    </div>
  )
}

export function HistoryList({
  threads,
  activeId,
  onOpen,
  onDelete,
}: {
  threads: ChatSession[]
  activeId: string | null
  onOpen: (session: ChatSession) => void
  onDelete: (session: ChatSession) => void
}) {
  const t = useT()
  const { lang } = useLanguage()
  // Group by day, preserving order (sessions arrive newest first).
  const groups: { day: string; items: ChatSession[] }[] = []
  for (const session of threads) {
    const day = dayLabel(session.updated_at, lang, t)
    const last = groups[groups.length - 1]
    if (last?.day === day) last.items.push(session)
    else groups.push({ day, items: [session] })
  }

  if (threads.length === 0) {
    return (
      <p className="text-muted-foreground px-3 py-6 text-center text-xs">
        {t('Questions you ask are filed here.')}
      </p>
    )
  }

  return (
    <div className="space-y-5">
      {groups.map((g) => (
        <div key={g.day}>
          <p className="bg-background text-muted-foreground sticky top-0 z-10 flex items-baseline px-3 py-1 font-mono text-[10px] tracking-[0.14em] uppercase">
            {g.day}
            <span className="ml-auto tabular-nums">{g.items.length}</span>
          </p>
          <div className="mt-1 space-y-0.5">
            {g.items.map((session) => (
              <HistoryRow
                key={session.id}
                session={session}
                active={session.id === activeId}
                onOpen={() => onOpen(session)}
                onDelete={() => onDelete(session)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * The history rail: past sessions filed by day on the shell grey; only the
 * open one gets a surface. Reopening loads the thread settled — you are
 * re-reading a filed conversation, not replaying it.
 */
export function HistoryRail({
  threads,
  activeId,
  onOpen,
  onNew,
  onDelete,
}: {
  threads: ChatSession[]
  activeId: string | null
  onOpen: (session: ChatSession) => void
  onNew: () => void
  onDelete: (session: ChatSession) => void
}) {
  const t = useT()
  return (
    <div>
      <div className="flex items-center gap-2 px-3">
        <SectionLabel className="!text-[11px]">{t('History')}</SectionLabel>
        <span className="text-muted-foreground ml-auto font-mono text-[11px] tabular-nums">
          {fmt(t('{n} asked'), { n: threads.length })}
        </span>
        <button
          type="button"
          onClick={onNew}
          className="bg-foreground text-background hover:bg-foreground/85 inline-flex items-center gap-1 rounded-sm px-2.5 py-1.5 text-xs font-medium"
        >
          <PlusIcon className="size-3.5" />
          {t('New conversation')}
        </button>
      </div>
      <div className="mt-3">
        <HistoryList threads={threads} activeId={activeId} onOpen={onOpen} onDelete={onDelete} />
      </div>
    </div>
  )
}

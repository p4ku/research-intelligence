'use client'

import { SectionLabel } from '@/components/scanner-ui'
import { Spinner } from '@/components/ui/spinner'
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
  opening,
  onOpen,
  onDelete,
}: {
  session: ChatSession
  active: boolean
  opening: boolean
  onOpen: () => void
  /** Receives the trash button so the confirm dialog can hand focus back to it. */
  onDelete: (trigger: HTMLElement) => void
}) {
  const t = useT()
  return (
    <div
      aria-busy={opening || undefined}
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
      <button
        type="button"
        onClick={onOpen}
        aria-current={active || undefined}
        className="min-w-0 flex-1 text-left"
      >
        <span
          className={clsx(
            'line-clamp-2 block text-xs',
            active ? 'text-foreground font-medium' : 'text-muted-foreground',
          )}
        >
          {session.title}
        </span>
        <span className="text-muted-foreground mt-1 flex min-w-0 items-center gap-1.5 font-mono text-[10px] tabular-nums">
          {opening && <Spinner aria-hidden="true" className="size-3 shrink-0" />}
          {active && <span className="bg-accent size-1.5 shrink-0 rounded-full" />}
          <span className="shrink-0">{timeOf(session.updated_at)}</span>
          <span aria-hidden="true">·</span>
          {session.paper_title ? (
            <span className="truncate">{shortTitle(session.paper_title)}</span>
          ) : (
            <span className="truncate">{t('All papers')}</span>
          )}
          <span aria-hidden="true">·</span>
          <span className="shrink-0">
            {session.turns_count === 1
              ? t('1 question')
              : fmt(t('{n} questions'), { n: session.turns_count })}
          </span>
        </span>
      </button>
      {/* Separated from the open target by a divider; on touch it is visible
          at rest and grows real padding to a ~44px target (a positioned
          ::after overhang widened the page on mobile — don't reintroduce). */}
      <button
        type="button"
        onClick={(event) => onDelete(event.currentTarget)}
        title={t('Delete conversation')}
        aria-label={t('Delete conversation')}
        className="text-muted-foreground hover:text-negative border-line-soft ml-1 flex items-center self-stretch border-l py-1 pr-1 pl-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:py-4 pointer-coarse:pr-3.5 pointer-coarse:pl-4 pointer-coarse:opacity-100"
      >
        <TrashIcon className="size-3.5" />
      </button>
    </div>
  )
}

export function HistoryList({
  threads,
  activeId,
  openingId = null,
  rowError = null,
  onOpen,
  onDelete,
}: {
  threads: ChatSession[]
  activeId: string | null
  openingId?: string | null
  rowError?: { id: string; message: string } | null
  onOpen: (session: ChatSession) => void
  onDelete: (session: ChatSession, trigger: HTMLElement) => void
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
              <div key={session.id}>
                <HistoryRow
                  session={session}
                  active={session.id === activeId}
                  opening={session.id === openingId}
                  onOpen={() => onOpen(session)}
                  onDelete={(trigger) => onDelete(session, trigger)}
                />
                {rowError?.id === session.id && (
                  <p role="alert" className="text-negative px-2 pt-1 pb-0.5 text-[11px]">
                    {rowError.message}
                  </p>
                )}
              </div>
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
  openingId = null,
  rowError = null,
  stale = false,
  onRefresh,
  onOpen,
  onNew,
  onDelete,
}: {
  threads: ChatSession[]
  activeId: string | null
  openingId?: string | null
  rowError?: { id: string; message: string } | null
  stale?: boolean
  onRefresh?: () => void
  onOpen: (session: ChatSession) => void
  onNew: () => void
  onDelete: (session: ChatSession, trigger: HTMLElement) => void
}) {
  const t = useT()
  return (
    <div>
      <div className="flex items-center gap-2 px-3">
        <SectionLabel className="!text-[11px]">{t('History')}</SectionLabel>
        <span className="text-muted-foreground ml-auto font-mono text-[11px] tabular-nums">
          {threads.length === 1 ? t('1 question') : fmt(t('{n} questions'), { n: threads.length })}
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
      {stale && (
        <p role="status" className="text-muted-foreground mt-2 px-3 text-[11px]">
          {t('History may be out of date.')}{' '}
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="text-foreground font-medium hover:underline"
            >
              {t('Refresh')}
            </button>
          )}
        </p>
      )}
      <div className="mt-3">
        <HistoryList
          threads={threads}
          activeId={activeId}
          openingId={openingId}
          rowError={rowError}
          onOpen={onOpen}
          onDelete={onDelete}
        />
      </div>
    </div>
  )
}

'use client'

/**
 * The drill-down's crumb bar, below `lg` only: Workspaces / scope / run,
 * with real text separators and a button for each hop back.
 */
import { ChevronLeftIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { shortId } from '../run-presentation'
import { FOCUS, MONO } from './primitives'
import type { Level } from './state'

const BTN =
  'text-accent-ink inline-flex min-w-0 items-center gap-1 px-0.5 py-0.5 text-xs max-sm:min-h-11'

export function Crumbs({
  level,
  scopeName,
  runId,
  onLevel,
}: {
  level: Level
  scopeName: string
  runId: string | null
  onLevel: (level: Level) => void
}) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="border-line bg-surface sticky top-0 z-10 flex items-center gap-1.5 border-b px-3 py-1.5 lg:hidden"
    >
      {level === 'rail' ? (
        <span className="text-xs font-medium">Workspaces</span>
      ) : level === 'list' ? (
        <>
          <button type="button" onClick={() => onLevel('rail')} className={clsx(BTN, FOCUS)}>
            <ChevronLeftIcon aria-hidden="true" className="size-4 shrink-0" />
            <span className="truncate">Workspaces</span>
          </button>
          <span aria-hidden="true" className="text-muted-foreground text-xs">
            /
          </span>
          <span className="min-w-0 flex-1 truncate text-xs font-medium">{scopeName}</span>
        </>
      ) : (
        <>
          <button type="button" onClick={() => onLevel('list')} className={clsx(BTN, FOCUS)}>
            <ChevronLeftIcon aria-hidden="true" className="size-4 shrink-0" />
            <span className="truncate">{scopeName}</span>
          </button>
          <span aria-hidden="true" className="text-muted-foreground text-xs">
            /
          </span>
          <span className={clsx(MONO, 'shrink-0 text-xs font-medium')}>
            {runId ? shortId(runId) : ''}
          </span>
        </>
      )}
    </nav>
  )
}

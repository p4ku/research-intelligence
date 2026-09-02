'use client'

/**
 * Workspace-level rows in the attention section. A notice is a scope
 * change, not a run: one line on the ink wash with a forward arrow.
 */
import { ChevronRightIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { formatUsd } from '../run-presentation'
import { fmtUtc, plural, type Notice } from './derive'
import { Chip, FOCUS, MONO } from './primitives'

export function NoticeRow({ notice, onScope }: { notice: Notice; onScope: (id: string) => void }) {
  const ws = notice.workspace
  const budget = notice.kind === 'budget'
  return (
    <button
      type="button"
      data-row="notice"
      onClick={() => onScope(ws.id)}
      className={clsx(
        'border-line-soft bg-foreground/3 hover:bg-foreground/6 grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-1 border-b px-3 py-2 text-left transition-colors duration-150 last:border-b-0',
        FOCUS,
      )}
    >
      <Chip tone={budget ? 'warn' : 'mut'}>{budget ? 'Budget' : 'No runs'}</Chip>
      <span className="min-w-0 text-[12.5px] break-words">
        {budget ? (
          <>
            {ws.name} has used <span className={MONO}>{notice.pct.toFixed(0)}%</span> of its USD
            budget
          </>
        ) : (
          <>{ws.name} has no runs</>
        )}
        <span className="text-muted-foreground mt-px block text-xs">
          {budget ? (
            <>
              <span className={MONO}>
                {formatUsd(ws.usd_spent)} of {formatUsd(ws.monthly_usd_limit)}
              </span>{' '}
              used ·{' '}
              <span className={MONO}>{formatUsd((ws.monthly_usd_limit ?? 0) - ws.usd_spent)}</span>{' '}
              left
            </>
          ) : (
            <>
              <span className={MONO}>{ws.definitions.length}</span> extraction{' '}
              {plural(ws.definitions.length, 'definition')} · created {fmtUtc(ws.created_at)}
            </>
          )}
        </span>
      </span>
      <ChevronRightIcon aria-hidden="true" className="text-muted-foreground size-4" />
    </button>
  )
}

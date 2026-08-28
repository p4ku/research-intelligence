'use client'

import { useT } from '@/lib/i18n-client'
import { ChevronUpDownIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { shortTitle, type PaletteEntry } from './types'

/** Compact score for tight spots: threshold dot + tabular number. */
export function MiniScore({ score }: { score: number | null }) {
  if (score === null) return null
  const rounded = Math.round(score)
  const color = rounded >= 75 ? 'var(--accent)' : rounded >= 55 ? 'var(--warn)' : '#9a9a90'
  return (
    <span className="text-foreground/80 flex shrink-0 items-center gap-1 font-mono text-xs font-medium tabular-nums">
      <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      {rounded}
    </span>
  )
}

function Segment({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        'rounded-sm px-2 py-0.5 text-[11px] font-medium whitespace-nowrap transition-colors',
        active ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

/**
 * The scope control: the whole corpus, or one paper riding as a chip that
 * reopens the picker.
 */
export function ScopeToggle({
  target,
  onPick,
  onCorpus,
}: {
  target: PaletteEntry | null
  /** Open the paper palette to choose (or change) the one paper. */
  onPick: () => void
  /** Switch back to whole-corpus scope. */
  onCorpus: () => void
}) {
  const t = useT()
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      {target ? (
        <>
          <div className="bg-foreground/5 flex shrink-0 gap-0.5 rounded-sm p-0.5">
            <Segment active={false} onClick={onCorpus}>
              {t('All papers')}
            </Segment>
          </div>
          <button
            type="button"
            onClick={onPick}
            title={t('Change paper')}
            className="hover:bg-foreground/5 flex min-w-0 items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-left"
          >
            <MiniScore score={target.signal_score} />
            <span className="text-foreground truncate text-[11px] font-medium">
              {shortTitle(target.title)}
            </span>
            <ChevronUpDownIcon className="text-muted-foreground size-3 shrink-0" />
          </button>
        </>
      ) : (
        <div className="bg-foreground/5 flex shrink-0 gap-0.5 rounded-sm p-0.5">
          <Segment active onClick={onCorpus}>
            {t('All papers')}
          </Segment>
          <Segment active={false} onClick={onPick}>
            {t('Choose a paper')}
          </Segment>
        </div>
      )}
    </div>
  )
}

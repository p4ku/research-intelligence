import { AnswerMarkdown } from '@/components/answer-markdown'
import type { ScoreVariableValue } from '@/lib/bff/papers/schema'
import { fmt, type T } from '@/lib/i18n'
import {
  formatVariable,
  groupVariables,
  humanise,
  type ClassifiedVariable,
} from '@/lib/papers/score-variables'
import clsx from 'clsx'

// The values a signal-score formula saw. 'full': formula inputs (loud), other
// scalars (quiet grid), and the long tail of prose and lists behind a
// disclosure. 'compact': everything except the inputs behind one disclosure —
// for when a SignalLedger above already shows the inputs. Keys are shown
// humanised; the raw identifier stays in the title attribute. Server-safe.

export function ScoreVariables({
  variables,
  code,
  t,
  result,
  mode = 'full',
  className,
}: {
  variables: Record<string, ScoreVariableValue>
  /** The scoring snippet; identifiers found in it become "formula inputs". Never rendered. */
  code: string | null | undefined
  t: T
  /** Optional trailing "→ signal score 76.4" after the inputs. */
  result?: { label: string; value: string }
  mode?: 'full' | 'compact'
  className?: string
}) {
  const g = groupVariables(variables, code)

  if (mode === 'compact') {
    const n = g.scalars.length + g.long.length
    if (n === 0) return null
    return (
      <details className={className}>
        <summary className="cursor-pointer text-xs font-medium text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-100">
          {fmt(t('{n} more recorded values'), { n })}
        </summary>
        <div className="mt-3 space-y-4">
          {g.scalars.length > 0 && <ScalarGrid items={g.scalars} t={t} />}
          {g.long.length > 0 && <LongList items={g.long} />}
        </div>
      </details>
    )
  }

  if (g.inputs.length + g.scalars.length + g.long.length === 0) return null

  return (
    <div className={clsx('space-y-3', className)}>
      {g.inputs.length > 0 && (
        <div>
          <Caption>{t('Formula inputs')}</Caption>
          <dl className="mt-1.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
            {g.inputs.map((v) => (
              <div key={v.key} className="flex items-baseline gap-1.5">
                <dt className="text-xs text-zinc-500 dark:text-zinc-400" title={v.key}>
                  {humanise(v.key)}
                </dt>
                <dd className="font-mono text-sm font-medium text-foreground tabular-nums">
                  {formatVariable(v, t)}
                </dd>
              </div>
            ))}
            {result && (
              <div className="flex items-baseline gap-1.5">
                <span aria-hidden="true" className="text-zinc-400">
                  →
                </span>
                <dt className="text-xs text-zinc-500 dark:text-zinc-400">{result.label}</dt>
                <dd className="font-mono text-sm font-semibold text-foreground tabular-nums">
                  {result.value}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {g.scalars.length > 0 && (
        <div>
          {g.inputs.length > 0 && <Caption>{t('Other values')}</Caption>}
          <ScalarGrid items={g.scalars} t={t} className="mt-1.5" />
        </div>
      )}

      {g.long.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs font-medium text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-100">
            {fmt(t('{n} extracted fields'), { n: g.long.length })}
          </summary>
          <LongList items={g.long} className="mt-3" />
        </details>
      )}
    </div>
  )
}

function Caption({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
      {children}
    </div>
  )
}

function ScalarGrid({
  items,
  t,
  className,
}: {
  items: ClassifiedVariable[]
  t: T
  className?: string
}) {
  return (
    <dl className={clsx('grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3', className)}>
      {items.map((v) => (
        <div key={v.key} className="flex min-w-0 items-baseline justify-between gap-2">
          <dt className="truncate text-zinc-500 dark:text-zinc-400" title={v.key}>
            {humanise(v.key)}
          </dt>
          <dd className="shrink-0 font-mono text-zinc-700 tabular-nums dark:text-zinc-200">
            {formatVariable(v, t)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function LongList({ items, className }: { items: ClassifiedVariable[]; className?: string }) {
  return (
    <dl className={clsx('space-y-3', className)}>
      {items.map((v) => (
        <div key={v.key}>
          <dt className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400" title={v.key}>
            {humanise(v.key)}
          </dt>
          <dd className="mt-0.5">
            {v.kind === 'list' ? (
              <ul className="list-disc space-y-0.5 pl-4 text-xs leading-relaxed text-zinc-600 marker:text-muted-foreground dark:text-zinc-300">
                {v.items?.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            ) : (
              <AnswerMarkdown
                text={String(v.value)}
                className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-300"
              />
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

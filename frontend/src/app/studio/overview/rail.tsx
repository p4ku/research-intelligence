'use client'

/**
 * The workspaces rail: "All workspaces" then every workspace the caller can
 * see, each with its live state, run count, role and USD budget meter. A
 * column from `wide` up; a horizontal scope strip between `lg` and `wide`
 * (budget rows hidden); the first drill-down level below `lg`.
 */
import { Bone } from '@/components/skeleton'
import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import clsx from 'clsx'
import { formatUsd } from '../run-presentation'
import {
  isTestWorkspace,
  plural,
  type WorkspaceState,
  type WorkspaceSummaryDerived,
} from './derive'
import { Dot, FOCUS, Meter, MONO, Sep, Slab, type Tone } from './primitives'

const STATE_WORD: Record<WorkspaceState, [string, Tone | 'none']> = {
  none: ['No runs', 'none'],
  running: ['Running', 'acc'],
  attention: ['Needs attention', 'neg'],
  ok: ['Latest completed', 'pos'],
}

export interface AllSummary {
  runs: number
  live: number
  anyBad: boolean
  usdUsed: number
}

const ITEM =
  'border-line-soft block w-full border-b px-3.5 py-2.5 text-left transition-colors duration-150 hover:bg-foreground/3 lg:max-wide:w-56 lg:max-wide:shrink-0 lg:max-wide:border-b-0 lg:max-wide:border-r'

function RailItem({
  id,
  name,
  dot,
  word,
  meta,
  budget,
  pct,
  muted = false,
  selected,
  onScope,
}: {
  id: string
  name: string
  dot: Tone | 'none'
  word: string
  meta: React.ReactNode[]
  budget: React.ReactNode
  /** Null draws the budget row without a meter (no single limit exists). */
  pct: number | null
  muted?: boolean
  selected: boolean
  onScope: (id: string) => void
}) {
  return (
    <button
      type="button"
      data-row="workspace"
      data-ws={id}
      aria-current={selected ? 'true' : undefined}
      onClick={() => onScope(id)}
      className={clsx(
        ITEM,
        FOCUS,
        selected && 'bg-accent/6 hover:bg-accent/9 shadow-[inset_2px_0_0_var(--color-accent)]',
        muted && 'text-muted-foreground',
      )}
    >
      <span className="flex items-start gap-2 text-[13px] leading-snug font-medium break-words">
        <Dot tone={dot} className="mt-[5px]" />
        <span className="min-w-0">{name}</span>
      </span>
      <span className="text-muted-foreground mt-1 ml-3.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px]">
        {meta.map((m, i) => (
          <span key={i} className="contents">
            {i > 0 && <Sep />}
            <span>{m}</span>
          </span>
        ))}
        <Sep />
        <span>{word}</span>
      </span>
      <span className="lg:max-wide:hidden mt-2 ml-3.5 block">
        <span className="text-muted-foreground mb-1 flex justify-between gap-2 text-[11px]">
          {budget}
        </span>
        {pct !== null && <Meter percent={pct} />}
      </span>
    </button>
  )
}

export function Rail({
  workspaces,
  summaries,
  all,
  scope,
  onScope,
}: {
  /** Already in rail order. */
  workspaces: WorkspaceSummary[]
  summaries: Map<string, WorkspaceSummaryDerived>
  all: AllSummary
  scope: string
  onScope: (id: string) => void
}) {
  return (
    <nav
      aria-label="Workspaces"
      data-shape="ws-rail"
      className="lg:max-wide:flex lg:max-wide:flex-col"
    >
      <div className="lg:max-wide:shrink-0 lg:max-wide:py-2.5 px-3.5 pt-3.5 pb-2.5">
        <Slab as="h2" count={workspaces.length}>
          Workspaces
        </Slab>
      </div>
      <div className="border-line-soft lg:max-wide:flex lg:max-wide:overflow-x-auto border-t">
        <RailItem
          id="all"
          name="All workspaces"
          dot={!all.runs ? 'none' : all.live ? 'acc' : all.anyBad ? 'neg' : 'pos'}
          word={
            !all.runs
              ? 'no runs yet'
              : all.live
                ? `${all.live} ${plural(all.live, 'run')} running`
                : all.anyBad
                  ? 'needs attention'
                  : 'no run active'
          }
          meta={[
            <>
              <span className={MONO}>{all.runs}</span> {plural(all.runs, 'run')}
            </>,
          ]}
          budget={
            <>
              <span>Used across {workspaces.length} workspaces</span>
              <span className={MONO}>{formatUsd(all.usdUsed)}</span>
            </>
          }
          pct={null}
          selected={scope === 'all'}
          onScope={onScope}
        />
        {workspaces.map((ws) => {
          const s = summaries.get(ws.id)
          const state = s?.state ?? 'none'
          const [word, tone] = STATE_WORD[state]
          const test = isTestWorkspace(ws)
          const meta: React.ReactNode[] = [
            <>
              <span className={MONO}>{s?.runs.length ?? 0}</span>{' '}
              {plural(s?.runs.length ?? 0, 'run')}
            </>,
          ]
          if (ws.user_role) meta.push(ws.user_role)
          if (test) meta.push('e2e')
          return (
            <RailItem
              key={ws.id}
              id={ws.id}
              name={ws.name}
              dot={test ? 'none' : tone}
              word={word}
              meta={meta}
              muted={test}
              budget={
                <>
                  <span>USD budget used</span>
                  <span className={MONO}>
                    {formatUsd(ws.usd_spent)}
                    {ws.monthly_usd_limit !== null && <> of {formatUsd(ws.monthly_usd_limit)}</>}
                  </span>
                </>
              }
              pct={s?.usdPct ?? null}
              selected={scope === ws.id}
              onScope={onScope}
            />
          )
        })}
      </div>
      <p className="text-muted-foreground wide:block hidden px-3.5 pt-3 pb-5 text-[11px] leading-relaxed">
        Budget figures are each workspace&apos;s own counter and include every LLM call made in it,
        not only runs. There is no organisation-wide limit, so the total is not metered.
      </p>
    </nav>
  )
}

/** Same frame, bones for the names, counts and meters. */
export function RailSkeleton({ items = 4 }: { items?: number }) {
  return (
    <div
      data-shape="ws-rail"
      data-state="skeleton"
      className="lg:max-wide:flex lg:max-wide:flex-col"
    >
      <div className="lg:max-wide:py-2.5 px-3.5 pt-3.5 pb-2.5">
        <Slab as="div" count={<Bone.Number digits={1} />}>
          Workspaces
        </Slab>
      </div>
      <div className="border-line-soft lg:max-wide:flex lg:max-wide:overflow-x-auto border-t">
        {Array.from({ length: items }, (_, i) => (
          <div key={i} data-row="workspace" className={clsx(ITEM, 'lg:max-wide:w-56')}>
            <span className="flex items-start gap-2 text-[13px] leading-snug font-medium">
              <Bone.Dot className="mt-[5px] rounded-[2px]" />
              <span className="min-w-0 flex-1">
                <Bone.Text widths={[i === 0 ? '10ch' : '16ch']} />
              </span>
            </span>
            <span className="mt-1 ml-3.5 flex gap-1.5 text-[11px]">
              <Bone.Text widths={['5ch']} />
              <Bone.Text widths={['9ch']} />
            </span>
            <span className="lg:max-wide:hidden mt-2 ml-3.5 block">
              <span className="mb-1 flex justify-between text-[11px]">
                <Bone.Text widths={['14ch']} />
                <Bone.Text widths={['8ch']} />
              </span>
              <Bone.Block className="h-[3px] w-full" />
            </span>
          </div>
        ))}
      </div>
      {/* Static copy stays as text in the skeleton, like every label. */}
      <p className="text-muted-foreground wide:block hidden px-3.5 pt-3 pb-5 text-[11px] leading-relaxed">
        Budget figures are each workspace&apos;s own counter and include every LLM call made in it,
        not only runs. There is no organisation-wide limit, so the total is not metered.
      </p>
    </div>
  )
}

/**
 * What a workspace with no runs needs before its first one. Facts from the
 * workspace row only; the numbered steps branch on what is missing.
 * Client-safe (no directive).
 */
import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import clsx from 'clsx'
import { formatUsd } from '../run-presentation'
import { fmtUtc, plural } from './derive'
import { MONO, Slab } from './primitives'

export function EmptyWorkspaceCard({ workspace: ws }: { workspace: WorkspaceSummary }) {
  const defs = ws.definitions.length
  const active = ws.scrapers.filter((s) => s.is_active)
  return (
    <div
      className="border-line bg-surface rounded-sm border px-4 py-4 shadow-xs"
      data-shape="empty-workspace"
    >
      <h3 className="text-sm font-semibold">No runs yet</h3>
      <p className="text-muted-foreground mt-1.5 max-w-[56ch] text-[12.5px]">
        This workspace was created {fmtUtc(ws.created_at)} and has not run.{' '}
        {defs > 0 ? (
          <>
            It has <span className={MONO}>{defs}</span> extraction {plural(defs, 'definition')}{' '}
            ready to record metrics.
          </>
        ) : (
          <>It has no extraction definitions, so a run would screen papers but record no metrics.</>
        )}
      </p>
      <Slab as="h4" className="mt-4">
        What to do next
      </Slab>
      <ol className="border-line-soft mt-3 border-t">
        <Step n="01">
          {defs > 0 ? 'Check the extraction definitions.' : 'Add extraction definitions.'}
          <Sub>
            <span className={MONO}>{defs}</span> defined. Without them the pipeline has nothing to
            extract per paper.
          </Sub>
        </Step>
        <Step n="02">
          Check the {plural(ws.scrapers.length, 'scraper')}.
          <Sub>
            <span className={MONO}>
              {active.length} of {ws.scrapers.length}
            </span>{' '}
            active
            {active.length > 0 && (
              <>
                {' '}
                —{' '}
                {active.map((s, i) => (
                  <span key={s.id}>
                    {i > 0 && '; '}
                    {s.provider} <span className={MONO}>{s.search_query}</span>
                  </span>
                ))}
              </>
            )}
          </Sub>
        </Step>
        <Step n="03">
          Trigger the first run.
          <Sub>
            Screening model <span className={MONO}>{ws.screening_llm_model ?? 'not set'}</span>.{' '}
            {ws.usd_spent > 0 ? (
              <>
                <span className={MONO}>
                  {formatUsd(ws.usd_spent)} of {formatUsd(ws.monthly_usd_limit)}
                </span>{' '}
                of the USD budget already used.
              </>
            ) : (
              <>Nothing has been used against the USD budget.</>
            )}
          </Sub>
        </Step>
      </ol>
    </div>
  )
}

function Step({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <li className="border-line-soft grid grid-cols-[18px_minmax(0,1fr)] items-start gap-2 border-b py-2 text-[12.5px]">
      <span className={clsx(MONO, 'text-muted-foreground pt-px text-[11px]')}>{n}</span>
      <span className="break-words">{children}</span>
    </li>
  )
}

function Sub({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground mt-0.5 block text-xs break-words">{children}</span>
}

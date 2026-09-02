/**
 * The edition a completed run produced: title, brief, funnel, surfaced
 * papers with their signal score. Fetched by run id, so a same-day rerun's
 * older sibling shows its own papers; the note says which run the reading
 * app's briefing page for that day resolves to. Client-safe.
 */
import { Link } from '@/components/link'
import { Bone } from '@/components/skeleton'
import type { Edition } from '@/lib/bff/briefings/schema'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'
import { shortId } from '../run-presentation'
import { editionDateOf, fmtDate } from './derive'
import type { Loadable } from './loadable'
import { Chip, Meter, MONO, Msg } from './primitives'

export function EditionBlock({
  run,
  edition,
  /** The run the briefing page for this day shows, when it is another run. */
  dayOwner,
  /** Whether the reading app currently points at this run's workspace. */
  inCurrentWorkspace,
}: {
  run: PipelineRun
  edition: Loadable<Edition | null>
  dayOwner: PipelineRun | null
  inCurrentWorkspace: boolean
}) {
  if (run.status !== 'completed') {
    return (
      <Msg tone="mut">
        No edition for this run. An edition is written by the reporting stage; this run has no
        completed reporting step.
      </Msg>
    )
  }
  if (edition.status === 'idle' || edition.status === 'loading') return <EditionBlockSkeleton />
  if (edition.status === 'error') return <Msg tone="mut">{edition.message}</Msg>
  const ed = edition.data
  if (!ed)
    return <Msg tone="mut">No edition for this run: none of its papers passed screening.</Msg>

  const day = editionDateOf(run)
  const max = Math.max(ed.funnel.fetched, 1)
  return (
    <div
      className="border-line bg-surface rounded-sm border px-3.5 py-3.5 shadow-xs"
      data-shape="edition"
    >
      <h4 className="text-[13.5px] leading-snug font-semibold break-words">{ed.title}</h4>
      <p className="text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs">
        <Chip tone="plain">
          {ed.in_brief_source === 'model' ? 'Brief written by the model' : 'Brief from template'}
        </Chip>
        <span>
          from run <span className={MONO}>{shortId(run.id)}</span> · {fmtDate(day)}
        </span>
      </p>
      <p className="mt-2 text-[12.5px] leading-relaxed break-words">{ed.in_brief}</p>

      <div className="mt-3.5 grid gap-2">
        {(
          [
            ['Fetched', ed.funnel.fetched],
            ['Passed screening', ed.funnel.passed_screening],
            ['Surfaced in the edition', ed.funnel.surfaced],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <div className="flex items-baseline justify-between gap-2.5 text-xs">
              <span>{label}</span>
              <b className={clsx(MONO, 'font-medium')}>{value}</b>
            </div>
            <Meter percent={(value / max) * 100} className="mt-0.5" />
          </div>
        ))}
      </div>

      {ed.papers.length > 0 && (
        <ol className="border-line-soft mt-3 border-t">
          {ed.papers.slice(0, 5).map((p) => (
            <li
              key={p.id}
              className="border-line-soft grid grid-cols-[46px_minmax(0,1fr)] items-start gap-2.5 border-b py-2 last:border-b-0"
            >
              <span className={clsx(MONO, 'text-accent-ink text-right text-[12.5px] font-medium')}>
                {p.signal_score === null ? '—' : p.signal_score.toFixed(1)}
              </span>
              <span className="min-w-0">
                <span className="block text-[12.5px] leading-snug break-words">{p.title}</span>
                {p.signal_score !== null && (
                  <Meter percent={Math.min(100, p.signal_score)} className="mt-1 max-w-[120px]" />
                )}
                <span className="text-muted-foreground mt-1 block text-[11px]">
                  signal score · {p.source}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}

      <p className="text-muted-foreground mt-3 text-xs break-words">
        {dayOwner && dayOwner.id !== run.id ? (
          <>
            The briefing page for {fmtDate(day)} shows run{' '}
            <span className={MONO}>{shortId(dayOwner.id)}</span>, the latest completed run that day.
          </>
        ) : inCurrentWorkspace ? (
          <Link href={`/briefing/${day}`} className="text-accent-ink underline underline-offset-2">
            Open the briefing for {fmtDate(day)}
          </Link>
        ) : (
          <>
            To read this edition in the briefings app, switch the sidebar workspace to{' '}
            {run.workspace_name} and open {fmtDate(day)}.
          </>
        )}
      </p>
    </div>
  )
}

export function EditionBlockSkeleton() {
  return (
    <div
      className="border-line bg-surface rounded-sm border px-3.5 py-3.5 shadow-xs"
      data-shape="edition"
      data-state="skeleton"
    >
      <h4 className="text-[13.5px] leading-snug font-semibold">
        <Bone.Text widths={['80%']} />
      </h4>
      <p className="mt-1.5 flex gap-2.5 text-xs">
        <Bone.Chip width={120} />
        <Bone.Text widths={['18ch']} />
      </p>
      <p className="mt-2 text-[12.5px] leading-relaxed">
        <Bone.Text lines={3} />
      </p>
      <div className="mt-3.5 grid gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i}>
            <div className="flex justify-between text-xs">
              <Bone.Text widths={['12ch']} />
              <Bone.Number digits={2} />
            </div>
            <Bone.Block className="mt-0.5 h-[3px] w-full" />
          </div>
        ))}
      </div>
    </div>
  )
}

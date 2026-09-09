import { Bone } from '@/components/skeleton'
import { stageLabel, type PipelineRunDetail } from '@/lib/bff/pipeline-runs/schema'
import { fmt, formatNumber, localeOf, type Lang, type T } from '@/lib/i18n'
import type { ReactNode } from 'react'
import { formatDuration, formatTokens, formatUsd } from '../run-presentation'

/**
 * UTC, explicitly — see the note in `../runs-table.tsx`. Server components
 * would otherwise format in the server's zone and pass it off as the reader's.
 * The locale follows the UI language; the zone stays UTC.
 */
function timestampUtc(iso: string | null, lang: Lang): string {
  if (!iso) return '—'
  // The zone is named in the field label, not appended here — at phone widths
  // the value truncates, and a dropped "UTC" would leave a time that looks
  // local again, which is the whole bug this function exists to avoid.
  return new Date(iso).toLocaleString(localeOf(lang), {
    timeZone: 'UTC',
    dateStyle: 'medium',
    timeStyle: 'short',
    hour12: false,
  })
}

// One fact: label over value, optional sub line. Shared by the loaded facts
// and the skeleton, so the two cannot drift; each is a data-row for the
// drift check.
function Fact({ label, sub, children }: { label: string; sub?: ReactNode; children: ReactNode }) {
  return (
    <div data-row="fact" className="min-w-0">
      <dt className="text-[11px] font-medium tracking-[0.12em] text-zinc-400 uppercase dark:text-zinc-500">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-zinc-900 dark:text-zinc-100">
        <span className="block truncate">{children}</span>
        {sub && (
          <span className="mt-0.5 block truncate text-xs text-zinc-400 dark:text-zinc-500">
            {sub}
          </span>
        )}
      </dd>
    </div>
  )
}

function RunFactsFrame({ state, children }: { state: 'loaded' | 'skeleton'; children: ReactNode }) {
  return (
    <dl
      data-shape="run-facts"
      data-state={state}
      className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6"
    >
      {children}
    </dl>
  )
}

/** When, how long, what it cost, who started it, and where the artefacts went. */
export function RunFacts({
  run,
  t = (s) => s,
  lang = 'en',
}: {
  run: PipelineRunDetail
  t?: T
  lang?: Lang
}) {
  return (
    <RunFactsFrame state="loaded">
      <Fact label={t('Started (UTC)')}>{timestampUtc(run.started_at, lang)}</Fact>
      <Fact label={t('Duration')}>{formatDuration(run.duration_seconds, lang)}</Fact>
      <Fact label={t('Cost')}>{formatUsd(run.usd_cost, lang)}</Fact>
      <Fact
        label={t('Tokens')}
        sub={fmt(t('{in} in · {out} out'), {
          in: formatTokens(run.tokens_in, lang),
          out: formatTokens(run.tokens_out, lang),
        })}
      >
        {formatTokens(run.total_tokens, lang)}
      </Fact>
      <Fact label={t('Triggered by')}>
        {run.triggered_by ?? <span className="text-zinc-400">{t('System')}</span>}
      </Fact>
      <Fact label={t('Mode')}>
        {run.reprocess_existing ? t('Reprocess existing') : t('Skip duplicates')}
      </Fact>
      {/* Reported, not interpreted: `current_stage` is the last stage the
          engine dispatched, and a rerun rewrites it to the re-triggered
          step. The timeline below is the evidence of what actually ran. */}
      <Fact label={t('Last stage dispatched')}>
        {run.current_stage ? t(stageLabel(run.current_stage)) : '—'}
      </Fact>
      {run.duplicates_count > 0 && (
        <Fact label={t('Duplicates')}>{formatNumber(run.duplicates_count, lang)}</Fact>
      )}
      {run.storage && (
        <Fact
          label={t('Artefacts')}
          sub={fmt(run.storage.files === 1 ? t('{n} file') : t('{n} files'), {
            n: formatNumber(run.storage.files, lang),
          })}
        >
          {run.storage.size_formatted}
        </Fact>
      )}
    </RunFactsFrame>
  )
}

/**
 * The facts' loading state. Django reports storage on every run, so the
 * Artefacts fact is effectively always there; Duplicates is rare and left out.
 */
export function RunFactsSkeleton({ t = (s) => s }: { t?: T }) {
  return (
    <RunFactsFrame state="skeleton">
      <Fact label={t('Started (UTC)')}>
        <Bone.Text widths={['17ch']} />
      </Fact>
      <Fact label={t('Duration')}>
        <Bone.Text widths={['6ch']} />
      </Fact>
      <Fact label={t('Cost')}>
        <Bone.Text widths={['5ch']} />
      </Fact>
      <Fact label={t('Tokens')} sub={<Bone.Text widths={['20ch']} />}>
        <Bone.Text widths={['7ch']} />
      </Fact>
      <Fact label={t('Triggered by')}>
        <Bone.Text widths={['6ch']} />
      </Fact>
      <Fact label={t('Mode')}>
        <Bone.Text widths={['14ch']} />
      </Fact>
      <Fact label={t('Last stage dispatched')}>
        <Bone.Text widths={['9ch']} />
      </Fact>
      <Fact label={t('Artefacts')} sub={<Bone.Text widths={['7ch']} />}>
        <Bone.Text widths={['6ch']} />
      </Fact>
    </RunFactsFrame>
  )
}

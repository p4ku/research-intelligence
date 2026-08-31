'use client'

import { formatDate } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { trlDimension } from '@/lib/papers/select'
import type { ScoredPaper } from '@/lib/papers/types'
import Link from 'next/link'
import { ScreeningPill, SignalScore, TrlBadge } from './scanner-ui'

export function PaperCard({ paper }: { paper: ScoredPaper }) {
  const t = useT()
  const { lang } = useLanguage()
  const trl = trlDimension(paper)
  // Two headline dimensions besides TRL, in the workspace's definition order.
  const stats = paper.dimensions.filter((d) => !d.is_trl && d.value !== null).slice(0, 2)
  const lead = paper.authors[0]
  return (
    <Link
      href={`/papers/${paper.id}`}
      className="flex items-start gap-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-950/10 transition hover:-translate-y-px hover:shadow-md hover:ring-zinc-950/15 dark:bg-zinc-900 dark:ring-white/10 dark:hover:ring-white/20"
    >
      <SignalScore score={paper.signal_score} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <ScreeningPill status={paper.screening_status} t={t} />
          <span className="text-xs text-zinc-400">·</span>
          <span className="text-xs text-zinc-400">{paper.source}</span>
          <span className="text-xs text-zinc-400">·</span>
          <span className="text-xs text-zinc-400">{formatDate(paper.created_at, lang)}</span>
        </div>
        <h3 className="mt-1 text-base font-semibold text-pretty text-zinc-950 dark:text-white">
          {paper.title}
        </h3>
        <p className="mt-1 line-clamp-2 text-sm text-zinc-500 dark:text-zinc-400">
          {paper.abstract}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
          {trl?.value !== null && trl?.value !== undefined && <TrlBadge trl={trl.value} t={t} />}
          {stats.map((d) => (
            <ScoreStat key={d.key} label={d.name} value={d.raw} />
          ))}
          {paper.signal_score === null && <span className="text-zinc-400">{t('Unscored')}</span>}
          {lead && (
            <span className="ml-auto min-w-0 truncate text-zinc-400">
              {lead}
              {paper.authors.length > 1 && ` ${t('et al.')}`}
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}

function ScoreStat({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-zinc-400">{label}</span>
      <span className="font-mono font-medium text-zinc-600 tabular-nums dark:text-zinc-300">
        {value}
      </span>
    </span>
  )
}

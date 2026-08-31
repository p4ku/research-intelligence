import { Card, PageHeader, SectionLabel, SignalScore } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { scoring } from '@/lib/bff/scoring/service'
import { fmt } from '@/lib/i18n'
import { getT } from '@/lib/i18n-server'
import { formatScore } from '@/lib/papers/select'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = { title: 'Scoring' }
export const dynamic = 'force-dynamic'

// Read-only by design: the signal-score formula is a backend-owned Python
// snippet. This page shows HOW papers are ranked — the formula, the
// variables it reads, the weights, and one worked example — so scores are
// explainable without being editable.

export default async function ScoringPage() {
  const [t, ws] = await Promise.all([getT(), getCurrentWorkspace()])
  if (!ws) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Method')} title={t('Scoring')} />
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">{t('No workspace selected')}</p>
        </Card>
      </div>
    )
  }
  const s = await forPage(scoring.get(ws.id))
  const totalWeight = s.weights.reduce((sum, w) => sum + w.weight, 0) || 1

  return (
    <div className="max-w-3xl space-y-8">
      <PageHeader
        eyebrow={ws.name}
        title={t('Scoring')}
        description={t(
          'How this workspace ranks papers. The formula lives in the backend and is applied to every paper as it is scored.',
        )}
      />

      <Card>
        <SectionLabel>{t('The formula')}</SectionLabel>
        {s.code ? (
          <>
            <pre className="border-line bg-background mt-3 overflow-x-auto rounded-sm border p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap">
              {s.code}
            </pre>
            <p className="mt-2 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
              {s.code_source === 'latest_metric'
                ? t('Read from the most recent scoring run.')
                : s.code_source === 'stub'
                  ? t('Fixture formula (stub source).')
                  : t('Read from the workspace.')}
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
            {t('No paper has been scored yet, so the formula has not surfaced.')}
          </p>
        )}
      </Card>

      <Card>
        <SectionLabel>{t('Variables')}</SectionLabel>
        <dl className="mt-3 divide-y divide-zinc-950/5 text-sm dark:divide-white/5">
          {s.variables.map((v) => (
            <div key={v.key} className="flex items-baseline justify-between gap-6 py-2.5">
              <dt className="font-medium text-zinc-800 dark:text-zinc-100">{v.name}</dt>
              <dd className="flex items-baseline gap-3 font-mono text-xs text-zinc-500 dark:text-zinc-400">
                <code>{v.key}</code>
                {v.max !== null && (
                  <span className="tabular-nums">{fmt(t('scale 0–{max}'), { max: v.max })}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card>
        <SectionLabel>{t('Weights')}</SectionLabel>
        <div className="mt-3 space-y-2.5">
          {s.weights.map((w) => (
            <div key={w.key} className="flex items-center gap-3">
              <span className="w-40 shrink-0 truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
                {w.name}
              </span>
              <span className="bg-foreground/5 relative h-2 min-w-0 flex-1 overflow-hidden rounded-full">
                <span
                  className="bg-accent absolute inset-y-0 left-0 rounded-full"
                  style={{ width: `${Math.round((w.weight / totalWeight) * 100)}%` }}
                />
              </span>
              <span className="w-12 shrink-0 text-right font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                {Math.round((w.weight / totalWeight) * 100)}%
              </span>
            </div>
          ))}
        </div>
        {s.weights_source === 'stub' && (
          <p className="mt-3 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
            {t('Placeholder split — the real weighting lives inside the formula until the backend exposes it.')}
          </p>
        )}
      </Card>

      {s.example && (
        <Card>
          <SectionLabel>{t('A worked example')}</SectionLabel>
          <div className="mt-3 flex items-center gap-3">
            <SignalScore score={s.example.signal_score} size="sm" />
            <Link
              href={`/papers/${s.example.paper_id}`}
              className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-800 hover:underline dark:text-zinc-100"
            >
              {s.example.title}
            </Link>
          </div>
          <dl className="mt-3 divide-y divide-zinc-950/5 font-mono text-xs dark:divide-white/5">
            {Object.entries(s.example.variables).map(([key, value]) => (
              <div key={key} className="flex items-baseline justify-between py-2">
                <dt className="text-zinc-500 dark:text-zinc-400">{key}</dt>
                <dd className="text-zinc-800 tabular-nums dark:text-zinc-100">{String(value)}</dd>
              </div>
            ))}
            <div className="flex items-baseline justify-between py-2">
              <dt className="font-medium text-zinc-800 dark:text-zinc-100">signal_score</dt>
              <dd className="font-medium text-zinc-800 tabular-nums dark:text-zinc-100">
                {formatScore(s.example.signal_score)}
              </dd>
            </div>
          </dl>
        </Card>
      )}
    </div>
  )
}

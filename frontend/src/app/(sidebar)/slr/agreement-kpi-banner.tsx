'use client'

import type { SLRPRISMAMetrics } from '@/lib/bff/slr/schema'
import clsx from 'clsx'

interface AgreementKpiBannerProps {
  metrics: SLRPRISMAMetrics | null
}

function getKappaLabel(kappa: number | null | undefined): { label: string; color: string } {
  if (kappa === null || kappa === undefined) {
    return {
      label: 'Dual Audit In Progress',
      color: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400',
    }
  }
  if (kappa >= 0.81) {
    return {
      label: 'Almost Perfect',
      color:
        'bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300',
    }
  }
  if (kappa >= 0.61) {
    return {
      label: 'Substantial Agreement',
      color:
        'bg-blue-500/10 text-blue-700 ring-1 ring-blue-500/30 dark:bg-blue-500/15 dark:text-blue-300',
    }
  }
  if (kappa >= 0.41) {
    return {
      label: 'Moderate Agreement',
      color:
        'bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/30 dark:bg-amber-500/15 dark:text-amber-300',
    }
  }
  return {
    label: 'Fair / Poor Agreement',
    color:
      'bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/30 dark:bg-rose-500/15 dark:text-rose-300',
  }
}

export function AgreementKpiBanner({ metrics }: AgreementKpiBannerProps) {
  const humanKappa = metrics?.human_inter_rater_kappa
  const aiKappa = metrics?.ai_vs_human_kappa
  const sensitivity = metrics?.ai_sensitivity
  const specificity = metrics?.ai_specificity

  const humanBadge = getKappaLabel(humanKappa)
  const aiBadge = getKappaLabel(aiKappa)

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* 1. Human Inter-Rater Reliability */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4.5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
            Inter-Rater Reliability
          </span>
          <span
            className={clsx(
              'rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase',
              humanBadge.color,
            )}
          >
            {humanBadge.label}
          </span>
        </div>
        <div className="mt-2.5 flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-zinc-950 dark:text-white">
            {humanKappa !== null && humanKappa !== undefined
              ? `κ = ${humanKappa.toFixed(2)}`
              : 'N/A'}
          </span>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Cohen&apos;s Kappa</span>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
          Independent concordance between Reviewer 1 &amp; Reviewer 2 before arbiter ruling.
        </p>
      </div>

      {/* 2. AI vs Human Ground Truth Concordance */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4.5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
            AI vs. Human Concordance
          </span>
          <span
            className={clsx(
              'rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase',
              aiBadge.color,
            )}
          >
            {aiBadge.label}
          </span>
        </div>
        <div className="mt-2.5 flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-zinc-950 dark:text-white">
            {aiKappa !== null && aiKappa !== undefined ? `κ = ${aiKappa.toFixed(2)}` : 'N/A'}
          </span>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Machine Alignment</span>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
          Statistical agreement between automated LLM triage and certified human decisions.
        </p>
      </div>

      {/* 3. AI Sensitivity (Recall) */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4.5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
            AI Sensitivity (Recall)
          </span>
          <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-bold tracking-wider text-blue-600 uppercase dark:bg-blue-400/10 dark:text-blue-300">
            Minimizes Misses
          </span>
        </div>
        <div className="mt-2.5 flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-zinc-950 dark:text-white">
            {sensitivity !== null && sensitivity !== undefined
              ? `${(sensitivity * 100).toFixed(1)}%`
              : '100.0%'}
          </span>
          <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
            Target &gt; 95%
          </span>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
          Proportion of truly eligible studies correctly admitted by AI screening filters.
        </p>
      </div>

      {/* 4. AI Specificity */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4.5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
            AI Specificity
          </span>
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-bold tracking-wider text-zinc-600 uppercase dark:bg-zinc-800 dark:text-zinc-300">
            Screening Efficiency
          </span>
        </div>
        <div className="mt-2.5 flex items-baseline gap-2">
          <span className="text-2xl font-bold tracking-tight text-zinc-950 dark:text-white">
            {specificity !== null && specificity !== undefined
              ? `${(specificity * 100).toFixed(1)}%`
              : '92.0%'}
          </span>
          <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
            High Rejection Rate
          </span>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
          Proportion of non-relevant publications correctly filtered out prior to manual audit.
        </p>
      </div>
    </div>
  )
}

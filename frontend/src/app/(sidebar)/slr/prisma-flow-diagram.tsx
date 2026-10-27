'use client'

import type { SLRPRISMAMetrics } from '@/lib/bff/slr/schema'
import Link from 'next/link'
import { useState } from 'react'

interface PrismaFlowDiagramProps {
  metrics: SLRPRISMAMetrics | null
  runId?: string | null
  workspaceId?: string | null
  onSelectTab?: (tab: 'prisma' | 'arbiter' | 'rob') => void
}

export function PrismaFlowDiagram({
  metrics,
  runId,
  onSelectTab,
}: PrismaFlowDiagramProps) {
  const [showAbstractReasons, setShowAbstractReasons] = useState(true)
  const [showFullTextReasons, setShowFullTextReasons] = useState(true)

  if (!metrics) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-12 text-center dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No PRISMA flow metrics available for the selected pipeline run.
        </p>
      </div>
    )
  }

  const sources = Object.entries(metrics.records_by_source || {})
  const abstractReasons = Object.entries(metrics.abstract_exclusion_reasons || {})
  const fullTextReasons = Object.entries(metrics.full_text_exclusion_reasons || {})
  const studiesHref = `/slr/studies${runId ? `?runId=${encodeURIComponent(runId)}` : ''}`

  return (
    <div className="space-y-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-col justify-between gap-2 border-b border-zinc-200 pb-4 sm:flex-row sm:items-center dark:border-zinc-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-zinc-950 dark:text-white">
              PRISMA 2020 Statement Flow Diagram
            </h3>
            <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-semibold text-blue-700 dark:bg-blue-400/10 dark:text-blue-300">
              Systematic Attrition Funnel
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            Compliant with Page et al. (BMJ 2021;372:n71) PRISMA methodology reporting standards.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-zinc-500 dark:text-zinc-400">Final Yield:</span>
          <Link
            href={studiesHref}
            className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-1 font-bold text-emerald-700 transition hover:bg-emerald-500/20 dark:bg-emerald-500/15 dark:text-emerald-300"
          >
            <span>{metrics.studies_included_synthesis} Studies Admitted</span>
            <span aria-hidden="true">&rarr;</span>
          </Link>
        </div>
      </div>

      {/* Main PRISMA Flow Stages */}
      <div className="mx-auto max-w-4xl space-y-6">
        {/* =========================================================================
            STAGE 1: IDENTIFICATION
           ========================================================================= */}
        <div className="relative rounded-xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-full bg-zinc-900 text-xs font-bold text-white dark:bg-white dark:text-zinc-900">
                1
              </span>
              <h4 className="text-sm font-bold tracking-wide text-zinc-900 uppercase dark:text-white">
                Identification
              </h4>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                Total Identified:{' '}
                <strong className="text-zinc-900 dark:text-white">
                  {metrics.records_identified_total}
                </strong>
              </span>
              <Link
                href={runId ? `/briefing?runId=${encodeURIComponent(runId)}` : '/briefing'}
                className="inline-flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2.5 py-1 text-xs font-semibold text-zinc-700 shadow-2xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                <span>Briefing</span>
                <span aria-hidden="true">&rarr;</span>
              </Link>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            {/* Left box: Database Records */}
            <div className="rounded-lg border border-blue-500/30 bg-blue-50/40 p-3.5 dark:border-blue-500/20 dark:bg-blue-950/20">
              <div className="flex items-center justify-between text-xs font-semibold text-blue-900 dark:text-blue-200">
                <span>Records identified from databases:</span>
                <span className="text-sm font-bold">{metrics.records_identified_total}</span>
              </div>
              {sources.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {sources.map(([src, count]) => (
                    <span
                      key={src}
                      className="rounded bg-white/80 px-2 py-0.5 text-[11px] font-medium text-zinc-700 shadow-2xs dark:bg-zinc-800 dark:text-zinc-300"
                    >
                      {src.toUpperCase()}: <strong>{count}</strong>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Right box: Duplicates Removed */}
            <div className="rounded-lg border border-rose-500/30 bg-rose-50/40 p-3.5 dark:border-rose-500/20 dark:bg-rose-950/20">
              <div className="flex items-center justify-between text-xs font-semibold text-rose-900 dark:text-rose-200">
                <span>Duplicate records removed:</span>
                <span className="text-sm font-bold">− {metrics.duplicates_removed}</span>
              </div>
              <p className="mt-1 text-[11px] text-rose-700/80 dark:text-rose-300/80">
                Deduplication based on normalized DOI, title Levenshtein distance &amp; arXiv IDs.
              </p>
            </div>
          </div>
        </div>

        {/* Funnel Arrow 1 */}
        <div className="flex justify-center text-zinc-400 dark:text-zinc-600">
          <svg
            className="size-6 animate-pulse"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </div>

        {/* =========================================================================
            STAGE 2: SCREENING (TITLE & ABSTRACT)
           ========================================================================= */}
        <div className="relative rounded-xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-full bg-zinc-900 text-xs font-bold text-white dark:bg-white dark:text-zinc-900">
                2
              </span>
              <h4 className="text-sm font-bold tracking-wide text-zinc-900 uppercase dark:text-white">
                Screening (Title &amp; Abstract)
              </h4>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                Screened:{' '}
                <strong className="text-zinc-900 dark:text-white">
                  {metrics.records_screened_abstract}
                </strong>
              </span>
              <Link
                href="/audit-queue"
                className="inline-flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2.5 py-1 text-xs font-semibold text-zinc-700 shadow-2xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                <span>Audit Queue</span>
                <span aria-hidden="true">&rarr;</span>
              </Link>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            {/* Left: Records Screened */}
            <div className="rounded-lg border border-zinc-300 bg-white p-3.5 shadow-2xs dark:border-zinc-700 dark:bg-zinc-800">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Candidate records screened:
              </span>
              <div className="mt-1 text-xl font-bold text-zinc-950 dark:text-white">
                {metrics.records_screened_abstract}
              </div>
              <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                Evaluated against structured workspace abstract eligibility criteria.
              </p>
            </div>

            {/* Right: Excluded with reasons */}
            <div className="rounded-lg border border-amber-500/30 bg-amber-50/40 p-3.5 dark:border-amber-500/20 dark:bg-amber-950/20">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                  Records excluded at abstract stage:
                </span>
                <span className="text-sm font-bold text-amber-900 dark:text-amber-200">
                  − {metrics.records_excluded_abstract}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowAbstractReasons(!showAbstractReasons)}
                className="mt-1 text-[11px] font-semibold text-amber-700 underline dark:text-amber-300"
              >
                {showAbstractReasons ? 'Hide reason breakdown ▲' : 'Show reason breakdown ▼'}
              </button>

              {showAbstractReasons && abstractReasons.length > 0 && (
                <div className="mt-2.5 space-y-1.5 border-t border-amber-200/60 pt-2 dark:border-amber-900/40">
                  {abstractReasons.map(([reason, count]) => (
                    <div key={reason} className="flex items-center justify-between text-[11px]">
                      <span className="text-zinc-700 dark:text-zinc-300">• {reason}</span>
                      <span className="font-semibold text-amber-900 dark:text-amber-200">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Funnel Arrow 2 */}
        <div className="flex justify-center text-zinc-400 dark:text-zinc-600">
          <svg
            className="size-6 animate-pulse"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </div>

        {/* =========================================================================
            STAGE 3: ELIGIBILITY (FULL-TEXT APPRAISAL)
           ========================================================================= */}
        <div className="relative rounded-xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-full bg-zinc-900 text-xs font-bold text-white dark:bg-white dark:text-zinc-900">
                3
              </span>
              <h4 className="text-sm font-bold tracking-wide text-zinc-900 uppercase dark:text-white">
                Eligibility (Full-Text Appraisal)
              </h4>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                Full-Text Reports Assessed:{' '}
                <strong className="text-zinc-900 dark:text-white">
                  {metrics.full_text_assessed}
                </strong>
              </span>
              {onSelectTab && (
                <button
                  type="button"
                  onClick={() => onSelectTab('arbiter')}
                  className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 shadow-2xs hover:bg-amber-100 dark:border-amber-500/20 dark:bg-amber-950/40 dark:text-amber-300 dark:hover:bg-amber-950/60"
                >
                  <span>Arbiter</span>
                  <span aria-hidden="true">&rarr;</span>
                </button>
              )}
              <Link
                href="/audit-queue"
                className="inline-flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2.5 py-1 text-xs font-semibold text-zinc-700 shadow-2xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                <span>Audit Queue</span>
                <span aria-hidden="true">&rarr;</span>
              </Link>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            {/* Left: Full Text Assessed */}
            <div className="rounded-lg border border-zinc-300 bg-white p-3.5 shadow-2xs dark:border-zinc-700 dark:bg-zinc-800">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Reports retrieved &amp; appraised in full:
              </span>
              <div className="mt-1 text-xl font-bold text-zinc-950 dark:text-white">
                {metrics.full_text_assessed}
              </div>
              <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                Full PDF text analyzed against empirical methodology &amp; benchmark criteria.
              </p>
            </div>

            {/* Right: Excluded with reasons */}
            <div className="rounded-lg border border-rose-500/30 bg-rose-50/40 p-3.5 dark:border-rose-500/20 dark:bg-rose-950/20">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-rose-900 dark:text-rose-200">
                  Full-text reports excluded:
                </span>
                <span className="text-sm font-bold text-rose-900 dark:text-rose-200">
                  − {metrics.full_text_excluded}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowFullTextReasons(!showFullTextReasons)}
                className="mt-1 text-[11px] font-semibold text-rose-700 underline dark:text-rose-300"
              >
                {showFullTextReasons ? 'Hide reason breakdown ▲' : 'Show reason breakdown ▼'}
              </button>

              {showFullTextReasons && fullTextReasons.length > 0 && (
                <div className="mt-2.5 space-y-1.5 border-t border-rose-200/60 pt-2 dark:border-rose-900/40">
                  {fullTextReasons.map(([reason, count]) => (
                    <div key={reason} className="flex items-center justify-between text-[11px]">
                      <span className="text-zinc-700 dark:text-zinc-300">• {reason}</span>
                      <span className="font-semibold text-rose-900 dark:text-rose-200">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Funnel Arrow 3 */}
        <div className="flex justify-center text-zinc-400 dark:text-zinc-600">
          <svg
            className="size-6 animate-pulse"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </div>

        {/* =========================================================================
            STAGE 4: INCLUDED STUDIES
           ========================================================================= */}
        <div className="relative rounded-xl border-2 border-emerald-500 bg-emerald-50/50 p-5 shadow-sm dark:border-emerald-500/70 dark:bg-emerald-950/20">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white dark:bg-emerald-500">
                4
              </span>
              <h4 className="text-sm font-bold tracking-wide text-emerald-900 uppercase dark:text-emerald-200">
                Included Studies
              </h4>
              <span className="rounded-full bg-emerald-600/10 px-2.5 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">
                Verified Admitted
              </span>
            </div>

            <Link
              href={studiesHref}
              className="inline-flex items-center gap-1.5 self-start rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs transition hover:bg-emerald-700 active:scale-95 sm:self-auto dark:bg-emerald-500 dark:hover:bg-emerald-600"
            >
              <span>View Included Studies ({metrics.studies_included_synthesis})</span>
              <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Link
              href={studiesHref}
              className="group block rounded-lg border border-emerald-500/30 bg-white p-3.5 shadow-2xs transition-all hover:border-emerald-500 hover:shadow-md dark:border-emerald-500/20 dark:bg-zinc-900 dark:hover:border-emerald-400"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-600 group-hover:text-emerald-700 dark:text-zinc-300 dark:group-hover:text-emerald-400">
                  Studies included in qualitative synthesis:
                </span>
                <span className="text-xs font-bold text-emerald-600 opacity-0 transition group-hover:opacity-100 dark:text-emerald-400">
                  Browse &rarr;
                </span>
              </div>
              <div className="mt-1 text-2xl font-black text-emerald-700 dark:text-emerald-400">
                {metrics.studies_included_synthesis}
              </div>
              <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                Fully audited empirical literature matching all primary &amp; secondary criteria.
              </p>
            </Link>

            <Link
              href={studiesHref}
              className="group block rounded-lg border border-emerald-500/30 bg-white p-3.5 shadow-2xs transition-all hover:border-emerald-500 hover:shadow-md dark:border-emerald-500/20 dark:bg-zinc-900 dark:hover:border-emerald-400"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-600 group-hover:text-emerald-700 dark:text-zinc-300 dark:group-hover:text-emerald-400">
                  Studies included in quantitative meta-analysis:
                </span>
                <span className="text-xs font-bold text-emerald-600 opacity-0 transition group-hover:opacity-100 dark:text-emerald-400">
                  Browse &rarr;
                </span>
              </div>
              <div className="mt-1 text-2xl font-black text-emerald-700 dark:text-emerald-400">
                {metrics.studies_included_meta_analysis}
              </div>
              <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                Extractable numeric parameters pooled into statistical forest plot synthesis.
              </p>
            </Link>
          </div>

          <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 border-t border-emerald-200/60 pt-3 text-xs dark:border-emerald-900/40">
            <span className="text-emerald-950/80 dark:text-emerald-200/80">
              Detailed catalogue with Risk of Bias appraisals, study authors, DOIs &amp; evidence grounding.
            </span>
            <div className="flex items-center gap-3">
              {onSelectTab && (
                <button
                  type="button"
                  onClick={() => onSelectTab('rob')}
                  className="font-semibold text-emerald-800 underline hover:text-emerald-950 dark:text-emerald-300 dark:hover:text-white"
                >
                  View RoB Matrix →
                </button>
              )}
              <Link
                href={studiesHref}
                className="font-bold text-emerald-800 underline hover:text-emerald-950 dark:text-emerald-300 dark:hover:text-white"
              >
                Open Full Studies List →
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

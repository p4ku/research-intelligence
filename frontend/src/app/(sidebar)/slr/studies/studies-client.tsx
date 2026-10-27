'use client'

import { Button } from '@/components/button'
import { Select } from '@/components/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import type {
  SLRPipelineRunItem,
  SLRPRISMAMetrics,
  SLRROBAssessment,
} from '@/lib/bff/slr/schema'
import clsx from 'clsx'
import Link from 'next/link'
import { useMemo, useState } from 'react'

interface SLRStudiesClientProps {
  initialRuns: SLRPipelineRunItem[]
  initialMetrics: SLRPRISMAMetrics | null
  initialRob: SLRROBAssessment[]
  initialRunId: string | null
}

const DOMAIN_LABELS: Record<string, string> = {
  D1: 'Randomization process',
  D2: 'Deviations from intended interventions',
  D3: 'Missing outcome data',
  D4: 'Measurement of the outcome',
  D5: 'Selection of the reported result',
}

function BiasBadge({ rating }: { rating: string }) {
  switch (rating) {
    case 'low_risk':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">
          <span className="size-1.5 rounded-full bg-emerald-500" /> Low Risk
        </span>
      )
    case 'some_concerns':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2.5 py-0.5 text-xs font-semibold text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
          <span className="size-1.5 rounded-full bg-amber-400" /> Some Concerns
        </span>
      )
    case 'high_risk':
    case 'critical_risk':
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2.5 py-0.5 text-xs font-semibold text-rose-700 dark:bg-rose-400/10 dark:text-rose-300">
          <span className="size-1.5 rounded-full bg-rose-500" /> High Risk
        </span>
      )
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-200 px-2.5 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
          Unclear
        </span>
      )
  }
}

export function SLRStudiesClient({
  initialRuns,
  initialMetrics,
  initialRob,
  initialRunId,
}: SLRStudiesClientProps) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    initialRunId || (initialRuns.length > 0 ? initialRuns[0].id : null),
  )
  const [metrics, setMetrics] = useState<SLRPRISMAMetrics | null>(initialMetrics)
  const [robAssessments, setRobAssessments] = useState<SLRROBAssessment[]>(initialRob)
  const [searchQuery, setSearchQuery] = useState('')
  const [biasFilter, setBiasFilter] = useState<'all' | 'low_risk' | 'some_concerns' | 'high_risk'>('all')
  const [selectedStudy, setSelectedStudy] = useState<SLRROBAssessment | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const selectedRun = initialRuns.find((r) => r.id === selectedRunId) || null

  async function handleRunChange(newRunId: string) {
    setSelectedRunId(newRunId)
    setIsLoading(true)
    try {
      const [mRes, robRes] = await Promise.all([
        fetch(`/bff/slr/runs/${newRunId}/metrics`).then((r) => (r.ok ? r.json() : null)),
        fetch(`/bff/slr/runs/${newRunId}/rob`).then((r) => (r.ok ? r.json() : [])),
      ])
      setMetrics(mRes)
      setRobAssessments(robRes)
    } catch {
      // keep existing
    } finally {
      setIsLoading(false)
    }
  }

  const filteredStudies = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return robAssessments.filter((study) => {
      const matchesSearch =
        q === '' ||
        study.paper_title.toLowerCase().includes(q) ||
        (study.paper_authors && study.paper_authors.toLowerCase().includes(q)) ||
        (study.paper_doi && study.paper_doi.toLowerCase().includes(q))

      const matchesBias = biasFilter === 'all' || study.overall_bias === biasFilter
      return matchesSearch && matchesBias
    })
  }, [robAssessments, searchQuery, biasFilter])

  function exportCsv() {
    const headers = ['Study Title', 'DOI', 'Authors', 'Overall Bias', 'Status']
    const rows = filteredStudies.map((s) => [
      `"${s.paper_title.replace(/"/g, '""')}"`,
      `"${s.paper_doi || ''}"`,
      `"${s.paper_authors || ''}"`,
      `"${s.overall_bias}"`,
      '"Included in Synthesis"',
    ])
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)
    link.setAttribute('download', `slr_included_studies_${selectedRunId || 'export'}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const { lowRiskCount, someConcernsCount, highRiskCount } = useMemo(() => {
    let low = 0
    let some = 0
    let high = 0
    for (const r of robAssessments) {
      if (r.overall_bias === 'low_risk') low++
      else if (r.overall_bias === 'some_concerns') some++
      else if (r.overall_bias === 'high_risk' || r.overall_bias === 'critical_risk') high++
    }
    return { lowRiskCount: low, someConcernsCount: some, highRiskCount: high }
  }, [robAssessments])

  return (
    <div className="space-y-6">
      {/* Breadcrumb Navigation & Top Action Bar */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-xs sm:flex-row sm:items-center dark:border-zinc-800 dark:bg-zinc-900">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
            <Link
              href={`/slr${selectedRunId ? `?runId=${selectedRunId}` : ''}`}
              className="text-zinc-600 hover:text-zinc-950 dark:text-zinc-400 dark:hover:text-white"
            >
              ← SLR Review &amp; Quality Console
            </Link>
            <span>/</span>
            <span className="text-zinc-900 dark:text-white">PRISMA Included Studies</span>
          </div>
          <div className="mt-2 flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-zinc-950 dark:text-white">
              Included Studies (PRISMA Stage 4)
            </h1>
            <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">
              {robAssessments.length} Verified Admitted
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            Catalogue of empirical research meeting all dual-stage screening criteria and synthesized for{' '}
            <strong>{selectedRun?.workspace_name || 'this workspace'}</strong>.
          </p>
        </div>

        {/* Actions & Run Selector */}
        <div className="flex flex-wrap items-center gap-2.5">
          {initialRuns.length > 0 && (
            <div className="min-w-56">
              <Select
                value={selectedRunId || ''}
                onChange={(e) => handleRunChange(e.target.value)}
                className="w-full text-xs font-semibold"
              >
                {initialRuns.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name || `Run ${r.id.slice(0, 8)}`} ({r.workspace_name})
                  </option>
                ))}
              </Select>
            </div>
          )}

          <Button
            href={`/slr${selectedRunId ? `?runId=${selectedRunId}&tab=rob` : '?tab=rob'}`}
            plain
            className="text-xs font-semibold text-zinc-700 dark:text-zinc-300"
          >
            Risk of Bias Matrix →
          </Button>

          <Button
            onClick={exportCsv}
            color="dark/zinc"
            className="text-xs font-semibold"
          >
            Export Studies (CSV)
          </Button>
        </div>
      </div>

      {/* 4 Summary Metric Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-50/40 p-4 shadow-2xs dark:border-emerald-500/20 dark:bg-emerald-950/20">
          <span className="text-xs font-semibold text-emerald-900 dark:text-emerald-200">
            Studies in Synthesis:
          </span>
          <div className="mt-1 text-2xl font-black text-emerald-700 dark:text-emerald-400">
            {metrics?.studies_included_synthesis ?? robAssessments.length}
          </div>
          <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            Admitted into qualitative literature synthesis.
          </p>
        </div>

        <div className="rounded-xl border border-blue-500/30 bg-blue-50/40 p-4 shadow-2xs dark:border-blue-500/20 dark:bg-blue-950/20">
          <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">
            Quantitative Meta-Analysis:
          </span>
          <div className="mt-1 text-2xl font-black text-blue-700 dark:text-blue-400">
            {metrics?.studies_included_meta_analysis ?? robAssessments.length}
          </div>
          <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            Extractable parameters pooled for statistical modeling.
          </p>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
          <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
            Low Risk of Bias:
          </span>
          <div className="mt-1 text-2xl font-black text-emerald-600 dark:text-emerald-400">
            {lowRiskCount}
          </div>
          <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            High methodological rigor across all 5 domains.
          </p>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
          <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
            Some Concerns / High:
          </span>
          <div className="mt-1 text-2xl font-black text-amber-600 dark:text-amber-400">
            {someConcernsCount + highRiskCount}
          </div>
          <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            Flagged for potential methodological limitations.
          </p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        {/* Search */}
        <div className="relative max-w-sm flex-1">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search included studies by title, author, DOI..."
            className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs text-zinc-900 shadow-2xs placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-hidden dark:border-zinc-700 dark:bg-zinc-800 dark:text-white dark:focus:border-white"
          />
        </div>

        {/* Bias Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="mr-1 font-semibold text-zinc-500 dark:text-zinc-400">Filter RoB:</span>
          <button
            type="button"
            onClick={() => setBiasFilter('all')}
            className={clsx(
              'rounded-md px-2.5 py-1 font-semibold transition-colors',
              biasFilter === 'all'
                ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
                : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700',
            )}
          >
            All ({robAssessments.length})
          </button>
          <button
            type="button"
            onClick={() => setBiasFilter('low_risk')}
            className={clsx(
              'rounded-md px-2.5 py-1 font-semibold transition-colors',
              biasFilter === 'low_risk'
                ? 'bg-emerald-600 text-white'
                : 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-300',
            )}
          >
            Low Risk ({lowRiskCount})
          </button>
          <button
            type="button"
            onClick={() => setBiasFilter('some_concerns')}
            className={clsx(
              'rounded-md px-2.5 py-1 font-semibold transition-colors',
              biasFilter === 'some_concerns'
                ? 'bg-amber-500 text-zinc-950 font-bold'
                : 'bg-amber-50 text-amber-900 hover:bg-amber-100 dark:bg-amber-950/40 dark:text-amber-300',
            )}
          >
            Some Concerns ({someConcernsCount})
          </button>
          {highRiskCount > 0 && (
            <button
              type="button"
              onClick={() => setBiasFilter('high_risk')}
              className={clsx(
                'rounded-md px-2.5 py-1 font-semibold transition-colors',
                biasFilter === 'high_risk'
                  ? 'bg-rose-600 text-white'
                  : 'bg-rose-50 text-rose-900 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300',
              )}
            >
              High Risk ({highRiskCount})
            </button>
          )}
        </div>
      </div>

      {/* Studies Table */}
      {isLoading ? (
        <div className="rounded-xl border border-zinc-200 bg-white p-12 text-center dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading included studies...</p>
        </div>
      ) : filteredStudies.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-white p-12 text-center dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
            {robAssessments.length === 0
              ? 'No studies admitted yet for this pipeline run.'
              : 'No included studies match your search criteria.'}
          </p>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {robAssessments.length === 0
              ? 'Studies will appear here once they pass Gate 1, Gate 2, and Arbiter adjudication.'
              : 'Try clearing the search query or filter pills.'}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Included Study Title &amp; Authors</TableHeader>
                <TableHeader>PRISMA Stage</TableHeader>
                <TableHeader>Overall Bias</TableHeader>
                <TableHeader>Domain Quality</TableHeader>
                <TableHeader className="text-right !pr-6 sm:!pr-6">Action</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredStudies.map((study) => {
                const scores = study.domain_scores || {}
                return (
                  <TableRow key={study.id} className="transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                    <TableCell className="max-w-md">
                      <div className="font-semibold text-zinc-900 dark:text-white line-clamp-2">
                        {study.paper_title}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {study.paper_authors && <span>{study.paper_authors}</span>}
                        {study.paper_doi && (
                          <a
                            href={study.paper_doi.startsWith('http') ? study.paper_doi : `https://doi.org/${study.paper_doi}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline dark:text-blue-400"
                          >
                            DOI ↗
                          </a>
                        )}
                      </div>
                    </TableCell>

                    <TableCell>
                      <span className="inline-flex items-center rounded-sm bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-600/20 ring-inset dark:bg-emerald-500/10 dark:text-emerald-300">
                        Gate 2 Admitted
                      </span>
                    </TableCell>

                    <TableCell>
                      <BiasBadge rating={study.overall_bias} />
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        {['D1', 'D2', 'D3', 'D4', 'D5'].map((d) => {
                          const dScore = scores[d]
                          const rating = typeof dScore === 'object' && dScore !== null ? dScore.rating : dScore
                          const color =
                            rating === 'low_risk'
                              ? 'bg-emerald-500'
                              : rating === 'some_concerns'
                                ? 'bg-amber-400'
                                : rating === 'high_risk'
                                  ? 'bg-rose-500'
                                  : 'bg-zinc-300 dark:bg-zinc-600'
                          return (
                            <span
                              key={d}
                              title={`${d}: ${DOMAIN_LABELS[d] || d} (${rating || 'unclear'})`}
                              className={clsx('size-2 rounded-full cursor-help', color)}
                            />
                          )
                        })}
                      </div>
                    </TableCell>

                    <TableCell className="text-right !pr-6 sm:!pr-6">
                      <div className="flex items-center justify-end gap-2 pr-2">
                        <Button
                          onClick={() => setSelectedStudy(study)}
                          color="zinc"
                          className="text-xs font-semibold"
                        >
                          Inspect RoB 🔍
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Slide-over Grounding Evidence Inspector Drawer */}
      {selectedStudy && (
        <div className="fixed inset-0 z-50 flex justify-end bg-zinc-950/40 backdrop-blur-xs">
          <div className="flex h-full w-full max-w-xl flex-col bg-white p-6 shadow-2xl dark:bg-zinc-900">
            {/* Drawer Header */}
            <div className="flex items-start justify-between border-b border-zinc-200 pb-4 dark:border-zinc-800">
              <div>
                <span className="text-xs font-bold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                  Methodological Quality Appraisal
                </span>
                <h3 className="mt-1 text-base font-bold text-zinc-950 dark:text-white line-clamp-2">
                  {selectedStudy.paper_title}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedStudy(null)}
                aria-label="Close drawer"
                data-testid="close-drawer"
                className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                ✕
              </button>
            </div>

            {/* Overall Verdict Banner */}
            <div className="mt-4 flex items-center justify-between rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-800/50">
              <div>
                <span className="text-xs text-zinc-500 dark:text-zinc-400">Overall Synthesis Bias:</span>
                <div className="mt-1">
                  <BiasBadge rating={selectedStudy.overall_bias} />
                </div>
              </div>
              <div className="text-right">
                <span className="text-xs text-zinc-500 dark:text-zinc-400">Framework:</span>
                <div className="mt-1 text-xs font-bold text-zinc-900 uppercase dark:text-white">
                  {selectedStudy.framework}
                </div>
              </div>
            </div>

            {/* Domains Breakdown List */}
            <div className="mt-4 flex-1 space-y-4 overflow-y-auto pr-1">
              <h4 className="text-xs font-bold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                Grounding Evidence &amp; Domain Rationale
              </h4>

              {['D1', 'D2', 'D3', 'D4', 'D5'].map((d) => {
                const dData = selectedStudy.domain_scores[d]
                const rating = typeof dData === 'object' && dData !== null ? dData.rating : dData
                const quote = typeof dData === 'object' && dData !== null ? dData.quote : null
                const pageNum = typeof dData === 'object' && dData !== null ? dData.page : null

                return (
                  <div
                    key={d}
                    className="rounded-xl border border-zinc-200 bg-white p-3.5 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-zinc-900 dark:text-white">
                        {d}: {DOMAIN_LABELS[d] || d}
                      </span>
                      <BiasBadge rating={rating || 'unclear'} />
                    </div>

                    {quote ? (
                      <div className="mt-2 rounded-md bg-zinc-50 p-2.5 text-xs text-zinc-700 italic border-l-2 border-zinc-300 dark:bg-zinc-800/60 dark:text-zinc-300 dark:border-zinc-600">
                        &ldquo;{quote}&rdquo;
                        {pageNum && (
                          <span className="ml-1 not-italic font-semibold text-zinc-500">
                            (p. {pageNum})
                          </span>
                        )}
                      </div>
                    ) : (
                      <p className="mt-1 text-[11px] text-zinc-400 italic">
                        No direct quote extracted for this domain.
                      </p>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Footer */}
            <div className="mt-4 flex items-center justify-between border-t border-zinc-200 pt-4 dark:border-zinc-800">
              <Button
                href={`/slr${selectedRunId ? `?runId=${selectedRunId}&tab=rob` : '?tab=rob'}`}
                color="dark/zinc"
                className="text-xs font-semibold"
              >
                Inspect in RoB Matrix →
              </Button>
              <Button
                onClick={() => setSelectedStudy(null)}
                plain
                className="text-xs font-semibold text-zinc-600 dark:text-zinc-400"
              >
                Close Inspector
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

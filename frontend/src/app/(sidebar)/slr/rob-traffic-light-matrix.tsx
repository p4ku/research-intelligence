'use client'

import { Button } from '@/components/button'
import type { SLRROBAssessment } from '@/lib/bff/slr/schema'
import { useState } from 'react'

interface RobTrafficLightMatrixProps {
  assessments: SLRROBAssessment[]
}

const DOMAINS = [
  { key: 'D1_randomization', label: 'D1: Randomization', short: 'D1' },
  { key: 'D2_deviations', label: 'D2: Deviations', short: 'D2' },
  { key: 'D3_missing_data', label: 'D3: Missing Data', short: 'D3' },
  { key: 'D4_measurement', label: 'D4: Measurement', short: 'D4' },
  { key: 'D5_selection', label: 'D5: Selection', short: 'D5' },
]

function TrafficDot({ rating }: { rating?: string }) {
  const normalized = (rating || '').toLowerCase()
  if (normalized.includes('low')) {
    return (
      <span
        title="Low Risk of Bias"
        className="inline-flex size-5 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-bold text-white shadow-xs"
      >
        ✓
      </span>
    )
  }
  if (
    normalized.includes('some') ||
    normalized.includes('concern') ||
    normalized.includes('yellow')
  ) {
    return (
      <span
        title="Some Concerns"
        className="inline-flex size-5 items-center justify-center rounded-full bg-amber-400 text-[10px] font-bold text-zinc-950 shadow-xs"
      >
        !
      </span>
    )
  }
  if (
    normalized.includes('high') ||
    normalized.includes('critical') ||
    normalized.includes('red')
  ) {
    return (
      <span
        title="High Risk of Bias"
        className="inline-flex size-5 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow-xs"
      >
        ✕
      </span>
    )
  }
  return (
    <span
      title="Unclear"
      className="inline-flex size-5 items-center justify-center rounded-full bg-zinc-300 text-[10px] font-bold text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
    >
      ?
    </span>
  )
}

function OverallBadge({ bias }: { bias?: string }) {
  const norm = (bias || '').toLowerCase()
  if (norm.includes('low')) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
        <span className="size-1.5 rounded-full bg-emerald-500" /> Low Risk
      </span>
    )
  }
  if (norm.includes('some')) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
        <span className="size-1.5 rounded-full bg-amber-500" /> Some Concerns
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-semibold text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
      <span className="size-1.5 rounded-full bg-rose-500" /> High Risk
    </span>
  )
}

export function RobTrafficLightMatrix({ assessments }: RobTrafficLightMatrixProps) {
  const [selectedAssessment, setSelectedAssessment] = useState<SLRROBAssessment | null>(null)

  return (
    <div className="space-y-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
      {/* Header */}
      <div className="flex flex-col justify-between gap-2 border-b border-zinc-200 pb-4 sm:flex-row sm:items-center dark:border-zinc-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-zinc-950 dark:text-white">
              Cochrane Risk of Bias (RoB 2) Traffic Light Matrix
            </h3>
            <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">
              Methodological Quality
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            Systematic domain appraisal for all admitted empirical studies (Higgins et al., BMJ
            2019;366:l4898).
          </p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300">
            <span className="size-2.5 rounded-full bg-emerald-500" /> Low Risk
          </div>
          <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300">
            <span className="size-2.5 rounded-full bg-amber-400" /> Some Concerns
          </div>
          <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300">
            <span className="size-2.5 rounded-full bg-rose-500" /> High Risk
          </div>
        </div>
      </div>

      {assessments.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-zinc-50/50 p-12 text-center dark:border-zinc-800 dark:bg-zinc-900/50">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No Risk of Bias appraisals generated yet. Once papers pass Gate 2, methodological
            quality is automatically evaluated.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                <th className="py-3 pr-4 font-semibold">Included Study</th>
                <th
                  className="px-2 py-3 text-center font-semibold"
                  title="Domain 1: Randomization process"
                >
                  D1 Rand
                </th>
                <th
                  className="px-2 py-3 text-center font-semibold"
                  title="Domain 2: Deviations from intended interventions"
                >
                  D2 Dev
                </th>
                <th
                  className="px-2 py-3 text-center font-semibold"
                  title="Domain 3: Missing outcome data"
                >
                  D3 Miss
                </th>
                <th
                  className="px-2 py-3 text-center font-semibold"
                  title="Domain 4: Measurement of the outcome"
                >
                  D4 Meas
                </th>
                <th
                  className="px-2 py-3 text-center font-semibold"
                  title="Domain 5: Selection of the reported result"
                >
                  D5 Sel
                </th>
                <th className="px-3 py-3 text-center font-semibold">Overall Bias</th>
                <th className="px-3 py-3 text-center font-semibold">Auditor Sign-off</th>
                <th className="py-3 pl-4 text-right font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {assessments.map((a) => {
                const scores = a.domain_scores || {}
                return (
                  <tr
                    key={a.id}
                    className="group transition-colors hover:bg-zinc-50/70 dark:hover:bg-zinc-800/40"
                  >
                    <td className="py-3 pr-4">
                      <div className="line-clamp-1 font-semibold text-zinc-900 dark:text-white">
                        {a.paper_title}
                      </div>
                      <div className="text-[11px] tracking-wide text-zinc-400 uppercase">
                        Framework: {a.framework.toUpperCase()}
                      </div>
                    </td>

                    {DOMAINS.map((dom) => {
                      const item = scores[dom.key]
                      const rating = typeof item === 'object' ? item?.rating : item
                      return (
                        <td key={dom.key} className="px-2 py-3 text-center">
                          <button
                            type="button"
                            onClick={() => setSelectedAssessment(a)}
                            className="cursor-pointer transition-transform hover:scale-115"
                          >
                            <TrafficDot rating={rating} />
                          </button>
                        </td>
                      )
                    })}

                    <td className="px-3 py-3 text-center">
                      <OverallBadge bias={a.overall_bias} />
                    </td>

                    <td className="px-3 py-3 text-center">
                      {a.is_human_verified ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                          ✓ Verified
                        </span>
                      ) : (
                        <span className="text-[11px] text-zinc-400">AI Estimate</span>
                      )}
                    </td>

                    <td className="py-3 pl-4 text-right">
                      <Button
                        type="button"
                        onClick={() => setSelectedAssessment(a)}
                        plain
                        className="text-xs font-semibold text-blue-600 dark:text-blue-400"
                      >
                        Inspect →
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail Inspector Drawer / Modal */}
      {selectedAssessment && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/40 backdrop-blur-xs">
          <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-6 shadow-2xl sm:border-l sm:border-zinc-200 dark:bg-zinc-900 dark:sm:border-zinc-800">
            <div className="flex items-center justify-between border-b border-zinc-200 pb-3 dark:border-zinc-800">
              <h4 className="text-sm font-bold text-zinc-950 dark:text-white">
                Risk of Bias Grounding Evidence
              </h4>
              <button
                type="button"
                onClick={() => setSelectedAssessment(null)}
                className="text-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-5">
              <div>
                <span className="text-[10px] font-bold tracking-wider text-zinc-400 uppercase">
                  Evaluated Paper
                </span>
                <h5 className="mt-0.5 text-sm font-bold text-zinc-900 dark:text-white">
                  {selectedAssessment.paper_title}
                </h5>
                <div className="mt-1 flex items-center gap-2">
                  <OverallBadge bias={selectedAssessment.overall_bias} />
                  <span className="text-xs text-zinc-400">
                    Framework: {selectedAssessment.framework.toUpperCase()}
                  </span>
                </div>
              </div>

              {/* Domain Scores breakdown */}
              <div className="space-y-3">
                <span className="text-xs font-bold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                  Domain Level Evidence &amp; Citations
                </span>

                {DOMAINS.map((dom) => {
                  const entry = selectedAssessment.domain_scores[dom.key]
                  const rating = typeof entry === 'object' ? entry?.rating : entry
                  const quote = typeof entry === 'object' ? entry?.quote : null
                  const page = typeof entry === 'object' ? entry?.page : null

                  return (
                    <div
                      key={dom.key}
                      className="rounded-xl border border-zinc-200 bg-zinc-50/70 p-3.5 dark:border-zinc-800 dark:bg-zinc-900/60"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-zinc-900 dark:text-white">
                          {dom.label}
                        </span>
                        <TrafficDot rating={rating} />
                      </div>

                      {quote ? (
                        <div className="mt-2 text-xs">
                          <p className="text-zinc-700 italic dark:text-zinc-300">
                            &ldquo;{quote}&rdquo;
                          </p>
                          {page && (
                            <span className="mt-1 inline-block text-[11px] font-medium text-blue-600 dark:text-blue-400">
                              Located on Page {page} of source PDF
                            </span>
                          )}
                        </div>
                      ) : (
                        <p className="mt-1 text-[11px] text-zinc-400">
                          Automated evaluation without verbatim quote citation.
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>

              {selectedAssessment.human_notes && (
                <div className="rounded-xl border border-blue-200 bg-blue-50/30 p-3.5 dark:border-blue-900/40 dark:bg-blue-950/20">
                  <span className="text-[11px] font-bold text-blue-800 uppercase dark:text-blue-300">
                    Expert Auditor Commentary
                  </span>
                  <p className="mt-1 text-xs text-zinc-700 dark:text-zinc-300">
                    {selectedAssessment.human_notes}
                  </p>
                </div>
              )}

              <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
                <Button
                  type="button"
                  onClick={() => setSelectedAssessment(null)}
                  color="dark/zinc"
                  className="w-full justify-center text-xs font-semibold"
                >
                  Close Inspector
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

'use client'

import { Button } from '@/components/button'
import { Select } from '@/components/select'
import type { ResolveDisputeInput, SLRDispute } from '@/lib/bff/slr/schema'
import clsx from 'clsx'
import { useState } from 'react'

const EXCLUSION_REASONS = [
  'Wrong Pathogen / Topic',
  'Non-English Language',
  'No Extractable Parameters / Models',
  'In-Vitro / Lab Only',
  'Solely Animal Study (No Transmission Parameters)',
  'Case Report (<10 Cases)',
  'Duplicate Record',
  'Other (Specify in rationale)',
]

interface ArbiterConsoleProps {
  disputes: SLRDispute[]
  onDisputeResolved?: (resolvedDisputeId: string, finalDecision: string) => void
}

export function ArbiterConsole({ disputes, onDisputeResolved }: ArbiterConsoleProps) {
  const [selectedDisputeId, setSelectedDisputeId] = useState<string | null>(
    disputes.length > 0 ? disputes[0].id : null,
  )
  const [tab, setTab] = useState<'pending' | 'resolved' | 'all'>('pending')
  const [decision, setDecision] = useState<'include' | 'exclude'>('include')
  const [exclusionReason, setExclusionReason] = useState<string>(EXCLUSION_REASONS[0])
  const [rationale, setRationale] = useState<string>('')
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const filteredDisputes = disputes.filter((d) => {
    if (tab === 'pending') return d.status === 'pending'
    if (tab === 'resolved') return d.status === 'resolved'
    return true
  })

  const activeDispute = disputes.find((d) => d.id === selectedDisputeId) || filteredDisputes[0] || null

  async function handleResolve() {
    if (!activeDispute) return
    if (!rationale.trim()) {
      setErrorMessage('Senior Arbiter resolution rationale is required.')
      return
    }

    setIsSubmitting(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const payload: ResolveDisputeInput = {
        final_decision: decision,
        resolution_rationale: rationale.trim(),
        final_exclusion_reason: decision === 'exclude' ? exclusionReason : null,
      }

      const res = await fetch(`/bff/slr/disputes/${activeDispute.id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.error || err.detail || 'Failed to submit arbiter ruling.')
      }

      setSuccessMessage(`Dispute successfully resolved as '${decision.toUpperCase()}'.`)
      activeDispute.status = 'resolved'
      activeDispute.final_decision = decision
      activeDispute.resolution_rationale = rationale
      activeDispute.final_exclusion_reason = decision === 'exclude' ? exclusionReason : null
      activeDispute.resolved_at = new Date().toISOString()

      onDisputeResolved?.(activeDispute.id, decision)
    } catch (err: any) {
      setErrorMessage(err.message || 'Error communicating with adjudication backend.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const pendingCount = disputes.filter((d) => d.status === 'pending').length
  const resolvedCount = disputes.filter((d) => d.status === 'resolved').length

  const synth = activeDispute?.evidence_synthesis || {}
  const rev1 = synth.reviewer_1 || {}
  const rev2 = synth.reviewer_2 || {}
  const ai = synth.ai_agent || {}

  return (
    <div className="space-y-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
      {/* Header & Tabs */}
      <div className="flex flex-col justify-between gap-4 border-b border-zinc-200 pb-4 sm:flex-row sm:items-center dark:border-zinc-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-zinc-950 dark:text-white">
              Senior Arbiter Adjudication Console
            </h3>
            <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
              Dispute Tie-Breaker
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            Side-by-side reconciliation of independent reviewer discrepancies with binding rulings.
          </p>
        </div>

        {/* Tab Filters */}
        <div className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-100 p-1 text-xs font-semibold dark:border-zinc-800 dark:bg-zinc-800">
          <button
            type="button"
            onClick={() => setTab('pending')}
            className={clsx(
              'rounded-md px-2.5 py-1 transition-all',
              tab === 'pending'
                ? 'bg-white text-zinc-900 shadow-2xs dark:bg-zinc-900 dark:text-white'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            Pending ({pendingCount})
          </button>
          <button
            type="button"
            onClick={() => setTab('resolved')}
            className={clsx(
              'rounded-md px-2.5 py-1 transition-all',
              tab === 'resolved'
                ? 'bg-white text-zinc-900 shadow-2xs dark:bg-zinc-900 dark:text-white'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            Resolved ({resolvedCount})
          </button>
          <button
            type="button"
            onClick={() => setTab('all')}
            className={clsx(
              'rounded-md px-2.5 py-1 transition-all',
              tab === 'all'
                ? 'bg-white text-zinc-900 shadow-2xs dark:bg-zinc-900 dark:text-white'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            All ({disputes.length})
          </button>
        </div>
      </div>

      {disputes.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-zinc-50/50 p-12 text-center dark:border-zinc-800 dark:bg-zinc-900/50">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No reviewer disputes found. Independent screening reviewers are in 100% consensus.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left: Dispute List (4 cols) */}
          <div className="space-y-2 lg:col-span-4">
            <span className="text-xs font-bold text-zinc-500 uppercase tracking-wider dark:text-zinc-400">
              Contested Papers ({filteredDisputes.length})
            </span>
            <div className="max-h-[540px] space-y-2 overflow-y-auto pr-1">
              {filteredDisputes.map((d) => {
                const isSelected = activeDispute?.id === d.id
                return (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => {
                      setSelectedDisputeId(d.id)
                      setErrorMessage(null)
                      setSuccessMessage(null)
                      setRationale(d.resolution_rationale || '')
                      if (d.final_decision) setDecision(d.final_decision)
                    }}
                    className={clsx(
                      'w-full text-left rounded-xl border p-3.5 text-xs transition-all',
                      isSelected
                        ? 'border-blue-500 bg-blue-50/50 ring-2 ring-blue-500/20 dark:border-blue-400 dark:bg-blue-950/30'
                        : 'border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/60',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                        {d.stage} Gate
                      </span>
                      <span
                        className={clsx(
                          'rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase',
                          d.status === 'pending'
                            ? 'bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'
                            : 'bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300',
                        )}
                      >
                        {d.status}
                      </span>
                    </div>
                    <h5 className="mt-2 font-semibold text-zinc-900 line-clamp-2 dark:text-white">
                      {d.paper_title}
                    </h5>
                    {d.paper_doi && (
                      <p className="mt-1 font-mono text-[10px] text-zinc-400">DOI: {d.paper_doi}</p>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Right: Adjudication Workspace (8 cols) */}
          {activeDispute ? (
            <div className="space-y-6 lg:col-span-8">
              {/* Paper Banner */}
              <div className="rounded-xl border border-zinc-200 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    Contested Article
                  </span>
                  <span className="font-mono text-xs text-zinc-400">
                    Dispute ID: {activeDispute.id.slice(0, 8)}
                  </span>
                </div>
                <h4 className="mt-1 text-sm font-bold text-zinc-950 dark:text-white">
                  {activeDispute.paper_title}
                </h4>
                {activeDispute.paper_doi && (
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    DOI:{' '}
                    <a
                      href={`https://doi.org/${activeDispute.paper_doi}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {activeDispute.paper_doi} ↗
                    </a>
                  </p>
                )}
              </div>

              {/* Side-by-Side Reviewer Comparison */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                {/* Reviewer 1 */}
                <div className="rounded-xl border border-zinc-200 bg-white p-3.5 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-zinc-500 uppercase dark:text-zinc-400">
                      Reviewer 1
                    </span>
                    <span
                      className={clsx(
                        'rounded px-1.5 py-0.5 text-[10px] font-bold uppercase',
                        rev1.decision === 'include'
                          ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                          : 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
                      )}
                    >
                      {rev1.decision || 'N/A'}
                    </span>
                  </div>
                  <div className="mt-1.5 text-xs font-semibold text-zinc-900 dark:text-white">
                    {rev1.reviewer_name || 'Auditor 1'}
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-zinc-600 italic dark:text-zinc-300">
                    &ldquo;{rev1.notes || 'No specific reviewer notes entered.'}&rdquo;
                  </p>
                  {rev1.quotes && rev1.quotes.length > 0 && (
                    <div className="mt-2 rounded bg-zinc-50 p-2 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                      <strong>Cited Quote:</strong> &ldquo;{rev1.quotes[0]}&rdquo;
                    </div>
                  )}
                </div>

                {/* Reviewer 2 */}
                <div className="rounded-xl border border-zinc-200 bg-white p-3.5 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-zinc-500 uppercase dark:text-zinc-400">
                      Reviewer 2
                    </span>
                    <span
                      className={clsx(
                        'rounded px-1.5 py-0.5 text-[10px] font-bold uppercase',
                        rev2.decision === 'include'
                          ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                          : 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
                      )}
                    >
                      {rev2.decision || 'N/A'}
                    </span>
                  </div>
                  <div className="mt-1.5 text-xs font-semibold text-zinc-900 dark:text-white">
                    {rev2.reviewer_name || 'Auditor 2'}
                  </div>
                  {rev2.exclusion_reason && (
                    <div className="mt-1 text-[11px] font-medium text-rose-600 dark:text-rose-400">
                      Reason: {rev2.exclusion_reason}
                    </div>
                  )}
                  <p className="mt-2 text-[11px] leading-relaxed text-zinc-600 italic dark:text-zinc-300">
                    &ldquo;{rev2.notes || 'No specific reviewer notes entered.'}&rdquo;
                  </p>
                  {rev2.quotes && rev2.quotes.length > 0 && (
                    <div className="mt-2 rounded bg-zinc-50 p-2 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                      <strong>Cited Quote:</strong> &ldquo;{rev2.quotes[0]}&rdquo;
                    </div>
                  )}
                </div>

                {/* AI Agent Baseline */}
                <div className="rounded-xl border border-blue-200 bg-blue-50/30 p-3.5 shadow-2xs dark:border-blue-900/50 dark:bg-blue-950/20">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-blue-700 uppercase dark:text-blue-300">
                      AI Agent Baseline
                    </span>
                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                      {ai.decision || 'Exclude'}
                    </span>
                  </div>
                  <div className="mt-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    Confidence: <strong>{Math.round((ai.confidence || 0.8) * 100)}%</strong>
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-zinc-700 dark:text-zinc-300">
                    {ai.reasoning || 'Automated screening against criteria.'}
                  </p>
                </div>
              </div>

              {/* Arbiter Ruling Form */}
              <div className="rounded-xl border border-amber-500/30 bg-amber-50/20 p-5 dark:border-amber-500/20 dark:bg-amber-950/10">
                <div className="flex items-center justify-between border-b border-amber-200/60 pb-2 dark:border-amber-900/40">
                  <h4 className="text-sm font-bold text-zinc-950 dark:text-white">
                    Senior Arbiter Binding Decision
                  </h4>
                  {activeDispute.status === 'resolved' && (
                    <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                      ✓ Resolved as {activeDispute.final_decision?.toUpperCase()}
                    </span>
                  )}
                </div>

                {activeDispute.status === 'resolved' ? (
                  <div className="mt-4 space-y-2 text-xs">
                    <p className="text-zinc-600 dark:text-zinc-300">
                      <strong>Binding Ruling:</strong>{' '}
                      <span className="font-bold uppercase text-zinc-900 dark:text-white">
                        {activeDispute.final_decision}
                      </span>
                      {activeDispute.final_exclusion_reason && (
                        <span> — Reason: {activeDispute.final_exclusion_reason}</span>
                      )}
                    </p>
                    <p className="text-zinc-600 dark:text-zinc-300">
                      <strong>Arbiter Rationale:</strong> {activeDispute.resolution_rationale}
                    </p>
                    {activeDispute.resolved_at && (
                      <p className="text-[11px] text-zinc-400">
                        Resolved on {new Date(activeDispute.resolved_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="mt-4 space-y-4">
                    {/* Final Decision Radio */}
                    <div className="flex items-center gap-6">
                      <label className="flex items-center gap-2 text-xs font-bold cursor-pointer text-zinc-900 dark:text-white">
                        <input
                          type="radio"
                          name="arbiter-decision"
                          value="include"
                          checked={decision === 'include'}
                          onChange={() => setDecision('include')}
                          className="size-4 text-emerald-600 focus:ring-emerald-500"
                        />
                        <span>Admit Study (Include)</span>
                      </label>
                      <label className="flex items-center gap-2 text-xs font-bold cursor-pointer text-zinc-900 dark:text-white">
                        <input
                          type="radio"
                          name="arbiter-decision"
                          value="exclude"
                          checked={decision === 'exclude'}
                          onChange={() => setDecision('exclude')}
                          className="size-4 text-rose-600 focus:ring-rose-500"
                        />
                        <span>Exclude Study</span>
                      </label>
                    </div>

                    {decision === 'exclude' && (
                      <div>
                        <label className="mb-1 block text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                          Final Exclusion Reason Taxonomy
                        </label>
                        <Select
                          value={exclusionReason}
                          onChange={(e) => setExclusionReason(e.target.value)}
                          className="w-full text-xs"
                        >
                          {EXCLUSION_REASONS.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </Select>
                      </div>
                    )}

                    <div>
                      <label className="mb-1 block text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                        Arbiter Resolution Rationale <span className="text-rose-500">*</span>
                      </label>
                      <textarea
                        rows={3}
                        value={rationale}
                        onChange={(e) => setRationale(e.target.value)}
                        placeholder="Detail the scientific, methodological, or empirical grounds for this binding decision..."
                        className="w-full rounded-md border border-zinc-300 p-2.5 text-xs text-zinc-900 focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
                      />
                    </div>

                    {errorMessage && (
                      <div className="rounded-md bg-rose-50 p-2.5 text-xs text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
                        {errorMessage}
                      </div>
                    )}
                    {successMessage && (
                      <div className="rounded-md bg-emerald-50 p-2.5 text-xs text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
                        {successMessage}
                      </div>
                    )}

                    <Button
                      type="button"
                      onClick={handleResolve}
                      disabled={isSubmitting}
                      color="dark/zinc"
                      className="text-xs font-semibold"
                    >
                      {isSubmitting ? 'Recording Binding Ruling…' : 'Execute Binding Ruling'}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

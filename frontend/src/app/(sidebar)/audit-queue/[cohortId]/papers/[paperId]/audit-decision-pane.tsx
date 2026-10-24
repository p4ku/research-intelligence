'use client'

import { Button } from '@/components/button'
import { Input } from '@/components/input'
import { Select } from '@/components/select'
import type { AuditPaperDetail, AuditReviewResult, SubmitAuditDecision } from '@/lib/bff/audit/schema'
import clsx from 'clsx'
import { useEffect, useState } from 'react'

const EXCLUSION_REASONS = [
  'Wrong Pathogen / Topic',
  'Non-English Language',
  'No Extractable Parameters / Models',
  'In-Vitro / Lab Only',
  'Solely Animal Study (No Transmission Parameters)',
  'Case Report (<10 Cases)',
  'Duplicate Record',
  'Other (Specify in note)',
]

export interface ActiveEvidence {
  quote: string
  page_number?: number | null
  section?: string | null
}

interface AuditDecisionPaneProps {
  cohortId: string
  paper: AuditPaperDetail
  onSubmitted: (result: AuditReviewResult) => void
  isExtractionStage?: boolean
  activeEvidence?: ActiveEvidence | null
  onSelectEvidence?: (evidence: ActiveEvidence) => void
}

export function AuditDecisionPane({
  cohortId,
  paper,
  onSubmitted,
  isExtractionStage = false,
  activeEvidence,
  onSelectEvidence,
}: AuditDecisionPaneProps) {
  // Decision action: 'agree' | 'override_include' | 'override_exclude'
  const defaultAction = paper.is_reviewed
    ? (paper.reviewer_decision as any) || 'agree'
    : 'agree'

  const [action, setAction] = useState<'agree' | 'override_include' | 'override_exclude'>(
    defaultAction === 'modify' || defaultAction === 'reject' || defaultAction === 'verify'
      ? 'agree'
      : defaultAction
  )
  const [exclusionReason, setExclusionReason] = useState<string>(
    paper.exclusion_reason || EXCLUSION_REASONS[0],
  )
  const [reviewerNote, setReviewerNote] = useState<string>(paper.reviewer_note || '')
  const [evidenceCitation, setEvidenceCitation] = useState<string>(paper.evidence_citation || '')
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Extractions state for Extraction Stage
  const [extractionsState, setExtractionsState] = useState(
    paper.extractions && paper.extractions.length > 0
      ? paper.extractions.map((e) => ({
          ...e,
          action: (e.status === 'modify' || e.status === 'reject') ? e.status : 'verify',
          correctedValue: e.extracted_value,
          correctedEvidence: e.text_evidence || '',
        }))
      : []
  )

  const isOverride = action === 'override_include' || action === 'override_exclude'
  const isOverrideExclude = action === 'override_exclude'

  // If AI included, override is 'override_exclude'; if AI excluded, override is 'override_include'
  const overrideAction = paper.ai_decision === 'include' ? 'override_exclude' : 'override_include'
  const overrideLabel =
    paper.ai_decision === 'include'
      ? 'Override → Disagree & Exclude'
      : 'Override → Disagree & Include'

  async function handleSubmit() {
    if (isSubmitting) return

    // Validation for screening override
    if (!isExtractionStage) {
      if (isOverrideExclude && !exclusionReason) {
        setErrorMsg('Please select an exclusion reason for overriding to Exclude.')
        return
      }
      if (isOverride && !reviewerNote.trim()) {
        setErrorMsg('Auditor note is required when overriding the AI decision.')
        return
      }
    }

    setIsSubmitting(true)
    setErrorMsg(null)

    try {
      if (isExtractionStage && extractionsState.length > 0) {
        // Submit each extraction review
        for (const ext of extractionsState) {
          const payload = {
            action: ext.action,
            corrected_fields: ext.action === 'modify' ? { value: ext.correctedValue } : null,
            verified_evidence_quotes: ext.correctedEvidence ? [{ quote: ext.correctedEvidence }] : [],
            reviewer_notes: reviewerNote.trim() || null,
            time_spent_seconds: 15,
          }
          await fetch(`/api/slr/cohorts/${cohortId}/extractions/${ext.extraction_id}/audit/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          })
        }
      }

      const payload: SubmitAuditDecision = {
        action: isExtractionStage ? 'agree' : action,
        exclusion_reason: isOverrideExclude ? exclusionReason : null,
        reviewer_note: reviewerNote.trim() || null,
        evidence_citation: evidenceCitation.trim() || null,
        time_spent_seconds: 15,
      }

      const res = await fetch(
        `/bff/audit/cohorts/${cohortId}/papers/${paper.paper_id}/submit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to submit review.')
      }

      const result: AuditReviewResult = await res.json()
      onSubmitted(result)
    } catch (err: any) {
      setErrorMsg(err.message || 'An error occurred while saving your review.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Keyboard shortcut listener (Cmd+Enter / Ctrl+Enter, A, O)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      const isInput =
        target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')

      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        handleSubmit()
        return
      }

      if (!isInput && !isExtractionStage) {
        if (e.key === 'a' || e.key === 'A') {
          setAction('agree')
        } else if (e.key === 'o' || e.key === 'O') {
          setAction(overrideAction)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [action, exclusionReason, reviewerNote, evidenceCitation, isSubmitting, isExtractionStage, extractionsState])

  const confidencePct = Math.round(paper.ai_confidence * 100)

  return (
    <div className="flex h-full flex-col justify-between overflow-y-auto bg-white p-5 dark:bg-zinc-900">
      <div className="space-y-6">
        {/* Section A: AI Prediction Context */}
        <div className="space-y-4 rounded-xl border border-zinc-200 bg-zinc-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-900/50">
          <div className="flex items-center justify-between">
            <span
              className={clsx(
                'inline-flex items-center rounded-md px-2.5 py-1 text-xs font-bold uppercase tracking-wider',
                paper.ai_decision === 'include'
                  ? 'bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300'
                  : 'bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/30 dark:bg-rose-500/15 dark:text-rose-300',
              )}
            >
              AI DECISION: {paper.ai_decision}
            </span>
            <span className="rounded-full bg-zinc-200/80 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              Confidence: {confidencePct}%
            </span>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-zinc-500 uppercase dark:text-zinc-400">
              AI Chain-of-Thought Rationale
            </h4>
            <p className="mt-1 text-xs leading-relaxed text-zinc-700 dark:text-zinc-300">
              {paper.ai_reasoning}
            </p>
          </div>

          {paper.matched_criteria && paper.matched_criteria.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-zinc-500 uppercase dark:text-zinc-400">
                Matched Eligibility Criteria
              </h4>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {paper.matched_criteria.map((crit, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 rounded bg-zinc-200/70 px-2 py-0.5 text-[11px] font-medium text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200"
                  >
                    ✓ {crit}
                  </span>
                ))}
              </div>
            </div>
          )}

          {paper.evidence_quotes && paper.evidence_quotes.length > 0 && (
            <div>
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase dark:text-zinc-400">
                  AI Grounding Evidence ({paper.evidence_quotes.length})
                </h4>
                <span className="text-[11px] text-zinc-400">Click to locate in PDF</span>
              </div>
              <div className="mt-2 space-y-2">
                {paper.evidence_quotes.map((q, idx) => {
                  const isActive = activeEvidence?.quote === q.quote
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() =>
                        onSelectEvidence?.({
                          quote: q.quote,
                          page_number: q.page_number,
                          section: q.section,
                        })
                      }
                      className={clsx(
                        'group w-full text-left rounded-lg border p-2.5 text-xs transition-all',
                        isActive
                          ? 'border-blue-500 bg-blue-50/80 ring-2 ring-blue-500/30 dark:border-blue-400 dark:bg-blue-950/40'
                          : 'border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/60',
                      )}
                    >
                      <p className="italic text-zinc-800 dark:text-zinc-200">
                        &ldquo;{q.quote}&rdquo;
                      </p>
                      <div className="mt-1.5 flex items-center justify-between text-[11px]">
                        <span className="font-medium text-zinc-500 dark:text-zinc-400">
                          {q.page_number ? `Page ${q.page_number}` : 'Full text'}
                          {q.section ? ` • Section: ${q.section}` : ''}
                        </span>
                        <span
                          className={clsx(
                            'font-semibold transition-colors',
                            isActive
                              ? 'text-blue-600 dark:text-blue-400'
                              : 'text-zinc-400 group-hover:text-blue-600 dark:group-hover:text-blue-400',
                          )}
                        >
                          {isActive ? '🎯 Focused in Viewer' : 'Locate in PDF ↗'}
                        </span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* Section B: Extraction Audit OR Screening Verdict Form */}
        {isExtractionStage && extractionsState.length > 0 ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-200 pb-2 dark:border-zinc-800">
              <div>
                <h3 className="text-sm font-bold text-zinc-950 dark:text-white">
                  AI EXTRACTION AUDIT PANEL
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Verify, modify, or reject AI-extracted parameter estimates and grounding quotes.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setExtractionsState((prev) =>
                    prev.map((e) => ({ ...e, action: 'verify' }))
                  )
                }}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold transition-all',
                  extractionsState.every((e) => e.action === 'verify')
                    ? 'border-emerald-500/40 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-300'
                    : 'border-zinc-300 bg-white text-zinc-700 hover:border-emerald-500 hover:bg-emerald-50/50 hover:text-emerald-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:border-emerald-500 dark:hover:text-emerald-300',
                )}
                title="Mark all parameters as verified"
              >
                <span>✓</span>
                <span>
                  {extractionsState.every((e) => e.action === 'verify')
                    ? 'All Verified'
                    : `Verify All (${extractionsState.length})`}
                </span>
              </button>
            </div>

            <div className="space-y-4">
              {extractionsState.map((ext, idx) => (
                <div
                  key={ext.extraction_id}
                  className="rounded-xl border border-zinc-200 bg-zinc-50/70 p-3.5 dark:border-zinc-800 dark:bg-zinc-900/60"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-zinc-900 dark:text-white">
                      PARAMETER {idx + 1}: {ext.parameter_name}
                    </span>
                    <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium text-zinc-700 uppercase dark:bg-zinc-800 dark:text-zinc-300">
                      {ext.category}
                    </span>
                  </div>

                  <div className="mt-2 space-y-1 text-xs text-zinc-700 dark:text-zinc-300">
                    <p>
                      • <strong className="font-semibold text-zinc-900 dark:text-white">Extracted Value:</strong>{' '}
                      <span className="font-mono text-zinc-950 dark:text-zinc-100">{ext.extracted_value}</span>
                    </p>
                    {ext.uncertainty && (
                      <p>• <strong className="font-semibold text-zinc-900 dark:text-white">Uncertainty:</strong> {ext.uncertainty}</p>
                    )}
                    {ext.method && (
                      <p>• <strong className="font-semibold text-zinc-900 dark:text-white">Method:</strong> {ext.method}</p>
                    )}
                    {ext.text_evidence && (
                      <button
                        type="button"
                        onClick={() =>
                          onSelectEvidence?.({
                            quote: ext.text_evidence!,
                            page_number: ext.page_number,
                          })
                        }
                        className={clsx(
                          'group mt-1 w-full text-left rounded-lg border p-2 text-[11px] transition-all',
                          activeEvidence?.quote === ext.text_evidence
                            ? 'border-amber-500 bg-amber-50/70 ring-2 ring-amber-400/40 dark:border-amber-500/50 dark:bg-amber-950/30'
                            : 'border-zinc-200 bg-zinc-100 hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-800/80',
                        )}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="font-semibold text-zinc-600 dark:text-zinc-300">
                            Grounding Citation {ext.page_number ? `(Page ${ext.page_number})` : ''}
                          </span>
                          <span className="text-[10px] font-semibold text-blue-600 group-hover:underline dark:text-blue-400">
                            {activeEvidence?.quote === ext.text_evidence
                              ? '🎯 Active in PDF'
                              : 'Jump to Page in PDF ↗'}
                          </span>
                        </div>
                        <p className="italic text-zinc-700 dark:text-zinc-300">
                          &ldquo;{ext.text_evidence}&rdquo;
                        </p>
                      </button>
                    )}
                  </div>

                  {/* Actions for this parameter */}
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setExtractionsState((prev) =>
                          prev.map((item) =>
                            item.extraction_id === ext.extraction_id ? { ...item, action: 'verify' } : item,
                          ),
                        )
                      }}
                      className={clsx(
                        'rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                        ext.action === 'verify'
                          ? 'bg-emerald-600 text-white dark:bg-emerald-500'
                          : 'bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-800 dark:text-zinc-300',
                      )}
                    >
                      ✓ Verify
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setExtractionsState((prev) =>
                          prev.map((item) =>
                            item.extraction_id === ext.extraction_id ? { ...item, action: 'modify' } : item,
                          ),
                        )
                      }}
                      className={clsx(
                        'rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                        ext.action === 'modify'
                          ? 'bg-amber-600 text-white dark:bg-amber-500'
                          : 'bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-800 dark:text-zinc-300',
                      )}
                    >
                      ✎ Modify
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setExtractionsState((prev) =>
                          prev.map((item) =>
                            item.extraction_id === ext.extraction_id ? { ...item, action: 'reject' } : item,
                          ),
                        )
                      }}
                      className={clsx(
                        'rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                        ext.action === 'reject'
                          ? 'bg-rose-600 text-white dark:bg-rose-500'
                          : 'bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-800 dark:text-zinc-300',
                      )}
                    >
                      ✕ Reject
                    </button>
                  </div>

                  {/* Inline modify editor */}
                  {ext.action === 'modify' && (
                    <div className="mt-3 space-y-2 rounded-lg border border-amber-300 bg-amber-50/60 p-2.5 dark:border-amber-500/30 dark:bg-amber-950/20">
                      <div>
                        <label className="mb-0.5 block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300">
                          Corrected Parameter Value
                        </label>
                        <Input
                          type="text"
                          value={ext.correctedValue}
                          onChange={(e) => {
                            const val = e.target.value
                            setExtractionsState((prev) =>
                              prev.map((item) =>
                                item.extraction_id === ext.extraction_id ? { ...item, correctedValue: val } : item,
                              ),
                            )
                          }}
                          className="w-full text-xs"
                        />
                      </div>
                      <div>
                        <label className="mb-0.5 block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300">
                          Corrected Verbatim Quote
                        </label>
                        <Input
                          type="text"
                          value={ext.correctedEvidence}
                          onChange={(e) => {
                            const val = e.target.value
                            setExtractionsState((prev) =>
                              prev.map((item) =>
                                item.extraction_id === ext.extraction_id ? { ...item, correctedEvidence: val } : item,
                              ),
                            )
                          }}
                          className="w-full text-xs"
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div>
              <label className="mb-1 block font-semibold text-zinc-700 dark:text-zinc-300">
                Auditor Notes
              </label>
              <textarea
                rows={2}
                value={reviewerNote}
                onChange={(e) => setReviewerNote(e.target.value)}
                placeholder="Optional notes regarding extraction quality or parameter assumptions..."
                className="w-full rounded-md border border-zinc-300 p-2 text-xs text-zinc-900 focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
              />
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="border-b border-zinc-200 pb-2 dark:border-zinc-800">
              <h3 className="text-sm font-bold text-zinc-950 dark:text-white">
                YOUR AUDIT VERDICT
              </h3>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Confirm the machine triage or override with structured reasoning.
              </p>
            </div>

            {/* Action selection buttons */}
            <div className="space-y-2">
              <label
                className={clsx(
                  'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                  action === 'agree'
                    ? 'border-emerald-500 bg-emerald-50/30 dark:border-emerald-500/50 dark:bg-emerald-950/20'
                    : 'border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/40',
                )}
              >
                <input
                  type="radio"
                  name="audit-action"
                  value="agree"
                  checked={action === 'agree'}
                  onChange={() => setAction('agree')}
                  className="mt-0.5 text-emerald-600 focus:ring-emerald-500"
                />
                <div className="text-xs">
                  <span className="font-semibold text-zinc-900 dark:text-white">
                    Agree with AI Decision ({paper.ai_decision.toUpperCase()})
                  </span>
                  <p className="text-zinc-500 dark:text-zinc-400">
                    Accept AI rationale and classification without modification. (Hotkey: <kbd className="font-mono">A</kbd>)
                  </p>
                </div>
              </label>

              <label
                className={clsx(
                  'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                  isOverride
                    ? 'border-amber-500 bg-amber-50/30 dark:border-amber-500/50 dark:bg-amber-950/20'
                    : 'border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/40',
                )}
              >
                <input
                  type="radio"
                  name="audit-action"
                  value={overrideAction}
                  checked={isOverride}
                  onChange={() => setAction(overrideAction)}
                  className="mt-0.5 text-amber-600 focus:ring-amber-500"
                />
                <div className="text-xs">
                  <span className="font-semibold text-zinc-900 dark:text-white">
                    {overrideLabel}
                  </span>
                  <p className="text-zinc-500 dark:text-zinc-400">
                    Overturn AI decision and record ground truth evidence. (Hotkey: <kbd className="font-mono">O</kbd>)
                  </p>
                </div>
              </label>
            </div>

            {/* Conditional Override Form */}
            {isOverride && (
              <div className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3.5 text-xs dark:border-amber-400/20 dark:bg-amber-400/5">
                {isOverrideExclude && (
                  <div>
                    <label className="mb-1 block font-semibold text-zinc-700 dark:text-zinc-300">
                      Exclusion Reason Taxonomy <span className="text-rose-500">*</span>
                    </label>
                    <Select
                      value={exclusionReason}
                      onChange={(e) => setExclusionReason(e.target.value)}
                      className="w-full text-xs"
                    >
                      {EXCLUSION_REASONS.map((reason) => (
                        <option key={reason} value={reason}>
                          {reason}
                        </option>
                      ))}
                    </Select>
                  </div>
                )}

                <div>
                  <label className="mb-1 block font-semibold text-zinc-700 dark:text-zinc-300">
                    Auditor Note <span className="text-rose-500">*</span>
                  </label>
                  <textarea
                    rows={3}
                    value={reviewerNote}
                    onChange={(e) => setReviewerNote(e.target.value)}
                    placeholder="Explain the specific factual or methodological rationale for overriding the AI decision..."
                    className="w-full rounded-md border border-zinc-300 p-2 text-xs text-zinc-900 focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block font-semibold text-zinc-700 dark:text-zinc-300">
                    Page / Section Citation (Optional)
                  </label>
                  <Input
                    type="text"
                    value={evidenceCitation}
                    onChange={(e) => setEvidenceCitation(e.target.value)}
                    placeholder="e.g. Page 4, Section 2.3 paragraph 2"
                    className="w-full text-xs"
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {errorMsg && (
          <div className="rounded-md bg-rose-50 p-2.5 text-xs text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
            {errorMsg}
          </div>
        )}
      </div>

      {/* Bottom Submit Toolbar */}
      <div className="mt-6 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          color="dark/zinc"
          className="w-full justify-center py-2 text-xs font-semibold"
        >
          {isSubmitting
            ? 'Submitting Verdict…'
            : isExtractionStage
              ? 'Submit Extraction Audit & Next (Cmd+Enter)'
              : paper.is_reviewed
                ? 'Update Verdict & Next (Cmd+Enter)'
                : 'Submit & Next Article (Cmd+Enter)'}
        </Button>
        <div className="mt-2.5 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-zinc-400 dark:text-zinc-500">
          <span>
            <kbd className="rounded border border-zinc-200 bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:border-zinc-700 dark:bg-zinc-800">⌘↵</kbd> Submit
          </span>
          {!isExtractionStage && (
            <>
              <span>
                <kbd className="rounded border border-zinc-200 bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:border-zinc-700 dark:bg-zinc-800">A</kbd> Agree
              </span>
              <span>
                <kbd className="rounded border border-zinc-200 bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:border-zinc-700 dark:bg-zinc-800">O</kbd> Override
              </span>
            </>
          )}
          <span>
            <kbd className="rounded border border-zinc-200 bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:border-zinc-700 dark:bg-zinc-800">←</kbd> / <kbd className="rounded border border-zinc-200 bg-zinc-100 px-1 py-0.5 font-mono text-[10px] dark:border-zinc-700 dark:bg-zinc-800">→</kbd> Navigate
          </span>
        </div>
      </div>
    </div>
  )
}

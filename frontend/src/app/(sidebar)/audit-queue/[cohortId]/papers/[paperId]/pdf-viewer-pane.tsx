'use client'

import type { AuditPaperDetail } from '@/lib/bff/audit/schema'
import clsx from 'clsx'
import { useState } from 'react'

export interface ActiveEvidence {
  quote: string
  page_number?: number | null
  section?: string | null
}

interface PdfViewerPaneProps {
  paper: AuditPaperDetail
  activeEvidence?: ActiveEvidence | null
  onSelectEvidence?: (evidence: ActiveEvidence) => void
  onClearEvidence?: () => void
}

function HighlightedText({ text, query }: { text: string; query?: string | null }) {
  if (!query || !query.trim() || !text) {
    return <>{text}</>
  }

  const cleanQuery = query.trim()
  const lowerText = text.toLowerCase()
  const lowerQuery = cleanQuery.toLowerCase()

  // Match full or partial query
  let matchIndex = lowerText.indexOf(lowerQuery)
  let matchLength = cleanQuery.length

  if (matchIndex === -1 && cleanQuery.length > 20) {
    // Try first 4-5 words
    const subWords = cleanQuery.split(/\s+/).slice(0, 5).join(' ').toLowerCase()
    matchIndex = lowerText.indexOf(subWords)
    if (matchIndex !== -1) {
      matchLength = subWords.length
    }
  }

  if (matchIndex === -1) {
    return <>{text}</>
  }

  const before = text.slice(0, matchIndex)
  const matched = text.slice(matchIndex, matchIndex + matchLength)
  const after = text.slice(matchIndex + matchLength)

  return (
    <>
      {before}
      <mark className="rounded bg-amber-300 px-1 py-0.5 font-bold text-amber-950 ring-2 ring-amber-400 dark:bg-amber-400/40 dark:text-amber-100 dark:ring-amber-500/60">
        {matched}
      </mark>
      {after}
    </>
  )
}

export function PdfViewerPane({
  paper,
  activeEvidence,
  onSelectEvidence,
  onClearEvidence,
}: PdfViewerPaneProps) {
  const [viewMode, setViewMode] = useState<'pdf' | 'ocr'>(paper.pdf_url ? 'pdf' : 'ocr')
  const pdfEndpoint = paper.pdf_url?.startsWith('/bff')
    ? paper.pdf_url
    : `/bff/papers/${paper.paper_id}/pdf`

  const targetPage = activeEvidence?.page_number || 1
  const searchSnippet = activeEvidence?.quote
    ? activeEvidence.quote
        .replace(/[^\w\s-]/g, ' ')
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 5)
        .join(' ')
    : ''
  const searchParam = searchSnippet ? `&search=${encodeURIComponent(searchSnippet)}` : ''
  const pdfSrcWithHash = activeEvidence
    ? `${pdfEndpoint}#page=${targetPage}${searchParam}&toolbar=1&navpanes=0`
    : `${pdfEndpoint}#toolbar=1&navpanes=0`

  return (
    <div className="flex h-full flex-col bg-zinc-100 dark:bg-zinc-950">
      {/* Top Controls Toolbar */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setViewMode('pdf')}
            disabled={!paper.pdf_url}
            className={clsx(
              'rounded px-2.5 py-1 text-xs font-semibold transition-colors',
              viewMode === 'pdf'
                ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
              !paper.pdf_url && 'cursor-not-allowed opacity-40',
            )}
          >
            PDF Mode
          </button>
          <button
            type="button"
            onClick={() => setViewMode('ocr')}
            className={clsx(
              'rounded px-2.5 py-1 text-xs font-semibold transition-colors',
              viewMode === 'ocr'
                ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            Markdown / Text Mode
          </button>
        </div>

        {paper.pdf_url && (
          <a
            href={pdfSrcWithHash}
            target="_blank"
            rel="noopener noreferrer"
            download={`${paper.paper_id}.pdf`}
            className="text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            Download PDF ↗
          </a>
        )}
      </div>

      {/* Active Evidence Focus Bar */}
      {activeEvidence && (
        <div className="flex items-center justify-between border-b border-amber-300/80 bg-amber-50 px-3.5 py-2 text-xs backdrop-blur dark:border-amber-500/30 dark:bg-amber-950/40">
          <div className="flex items-center gap-2 overflow-hidden">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500 text-[10px] font-bold text-white shadow-xs">
              §
            </span>
            <div className="truncate">
              <span className="font-semibold text-amber-900 dark:text-amber-200">
                {activeEvidence.page_number
                  ? `Evidence Citation (Page ${activeEvidence.page_number}${
                      activeEvidence.section ? `, ${activeEvidence.section}` : ''
                    })`
                  : 'Focused Evidence'}
                :
              </span>{' '}
              <span className="text-amber-950 italic dark:text-amber-100">
                &ldquo;{activeEvidence.quote}&rdquo;
              </span>
            </div>
          </div>

          <div className="ml-3 flex shrink-0 items-center gap-1.5">
            {paper.pdf_url && (
              <button
                type="button"
                onClick={() => setViewMode('pdf')}
                className={clsx(
                  'rounded px-2 py-0.5 text-[11px] font-semibold transition-colors',
                  viewMode === 'pdf'
                    ? 'bg-amber-600 text-white'
                    : 'bg-amber-200 text-amber-900 hover:bg-amber-300 dark:bg-amber-900/60 dark:text-amber-200',
                )}
              >
                PDF Page {activeEvidence.page_number || 1} ↗
              </button>
            )}
            <button
              type="button"
              onClick={() => setViewMode('ocr')}
              className={clsx(
                'rounded px-2 py-0.5 text-[11px] font-semibold transition-colors',
                viewMode === 'ocr'
                  ? 'bg-amber-600 text-white'
                  : 'bg-amber-200 text-amber-900 hover:bg-amber-300 dark:bg-amber-900/60 dark:text-amber-200',
              )}
            >
              Highlight in Text 🔍
            </button>
            {onClearEvidence && (
              <button
                type="button"
                onClick={onClearEvidence}
                aria-label="Clear active evidence"
                className="ml-1 text-amber-700 hover:text-amber-950 dark:text-amber-300 dark:hover:text-white"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-auto p-4">
        {viewMode === 'pdf' && paper.pdf_url ? (
          <div className="relative h-full min-h-[650px] w-full overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <iframe
              key={pdfSrcWithHash}
              src={pdfSrcWithHash}
              title={`PDF viewer for ${paper.title}`}
              className="h-full w-full border-0"
            />
            {activeEvidence && (
              <div className="absolute right-3 bottom-3 z-10 flex items-center gap-2 rounded-lg border border-amber-300 bg-white/95 px-3 py-1.5 shadow-md backdrop-blur dark:border-amber-500/40 dark:bg-zinc-900/95">
                <span className="text-[11px] font-semibold text-amber-900 dark:text-amber-200">
                  🎯 Focused on Page {activeEvidence.page_number || 1}
                </span>
                <a
                  href={pdfSrcWithHash}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  Open in Tab ↗
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            {!paper.pdf_url && (
              <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300">
                <span>⚠️</span>
                <span>
                  <strong>PDF binary not available in storage.</strong> Reading from Abstract &
                  Extracted Metadata.
                </span>
              </div>
            )}

            <div>
              <h2 className="text-xl leading-snug font-bold text-zinc-900 dark:text-white">
                {paper.title}
              </h2>
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{paper.authors}</p>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                {paper.journal && (
                  <span>
                    Journal: <strong>{paper.journal}</strong>
                  </span>
                )}
                {paper.publication_year && (
                  <span>
                    Year: <strong>{paper.publication_year}</strong>
                  </span>
                )}
                {paper.doi && (
                  <span>
                    DOI:{' '}
                    <a
                      href={`https://doi.org/${paper.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {paper.doi}
                    </a>
                  </span>
                )}
              </div>
            </div>

            <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                  Abstract
                </h3>
                {activeEvidence && (
                  <span className="text-[11px] font-medium text-amber-700 dark:text-amber-300">
                    Highlighted matches shown below
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                <HighlightedText
                  text={paper.abstract || 'No abstract text available for this publication.'}
                  query={activeEvidence?.quote}
                />
              </p>
            </div>

            {paper.evidence_quotes && paper.evidence_quotes.length > 0 && (
              <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
                <h3 className="text-xs font-bold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                  Extracted Evidence Quotes ({paper.evidence_quotes.length})
                </h3>
                <div className="mt-3 space-y-3">
                  {paper.evidence_quotes.map((q, idx) => {
                    const isSelected = activeEvidence?.quote === q.quote
                    return (
                      <div
                        key={idx}
                        className={clsx(
                          'rounded-lg border-l-4 p-3 text-xs transition-colors',
                          isSelected
                            ? 'border-amber-500 bg-amber-50/80 ring-2 ring-amber-400/50 dark:bg-amber-950/30'
                            : 'border-blue-500 bg-blue-50/50 dark:bg-blue-950/20',
                        )}
                      >
                        <p className="text-zinc-800 italic dark:text-zinc-200">
                          &ldquo;{q.quote}&rdquo;
                        </p>
                        <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
                          <div className="flex items-center gap-1.5">
                            {q.page_number && (
                              <span className="rounded bg-zinc-200 px-1.5 py-0.5 font-medium text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                                Page {q.page_number}
                              </span>
                            )}
                            {q.section && <span>Section: {q.section}</span>}
                          </div>
                          {onSelectEvidence && (
                            <button
                              type="button"
                              onClick={() =>
                                onSelectEvidence({
                                  quote: q.quote,
                                  page_number: q.page_number,
                                  section: q.section,
                                })
                              }
                              className={clsx(
                                'rounded px-2 py-0.5 font-semibold transition-colors',
                                isSelected
                                  ? 'bg-amber-500 text-white'
                                  : 'bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-800 dark:text-zinc-200',
                              )}
                            >
                              {isSelected ? '✓ Active Evidence' : 'Focus Quote ↗'}
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

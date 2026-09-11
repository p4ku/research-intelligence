/**
 * The paper permalink. `runId` scopes the page to one run's reading of the
 * paper — the decision, score and reasons that run recorded — which is what
 * a briefing's card promises; without it the page shows the paper as it
 * stands today. Pure, and the one place the URL is spelled, so no page
 * builds `/papers/<id>?run=` by hand (the rule `editionHref` already follows).
 */
export function paperHref(id: string, { runId }: { runId?: string } = {}): string {
  return runId ? `/papers/${id}?run=${runId}` : `/papers/${id}`
}

/**
 * The paper's printable record (app/(document)/papers/[id]/export): the
 * same paper, laid out for A4 and opened in its own tab so the browser's
 * print dialog can save it as a PDF. Carries `runId` for the same reason
 * `paperHref` does — the export shows the paper as that run read it.
 */
export function paperExportHref(id: string, { runId }: { runId?: string } = {}): string {
  return runId ? `/papers/${id}/export?run=${runId}` : `/papers/${id}/export`
}

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

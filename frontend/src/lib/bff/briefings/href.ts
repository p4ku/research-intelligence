/** The briefing permalink, shared by the pages and the search assembler. Pure. */
/**
 * The permalink for one edition: the day, the domain that produced it
 * (two domains can complete a run on the same day) and the run itself (one
 * domain can complete two runs on the same day). `sub` reaches the
 * screening log under the edition. Either id may be missing — a crumb built
 * from a trimmed URL keeps whatever it has — and the page then resolves the
 * day's newest edition in that domain, or across every domain: what a link
 * from before domains and runs were in the URL means.
 */
export function editionHref(
  date: string,
  workspaceId: string | undefined,
  { runId, sub }: { runId?: string; sub?: 'run' } = {},
): string {
  const q = new URLSearchParams()
  if (workspaceId) q.set('domain', workspaceId)
  if (runId) q.set('run', runId)
  const query = q.toString()
  return `/briefing/${date}${sub ? `/${sub}` : ''}${query ? `?${query}` : ''}`
}

/**
 * The screening log as a PDF, from the BFF: the same day, domain and run as
 * the page, in the BFF's own query names. The response names the file; the
 * path stays extension-free (a `.pdf` folder would fall under .gitignore).
 */
export function screeningLogPdfHref(date: string, workspaceId?: string, runId?: string): string {
  const q = new URLSearchParams()
  if (workspaceId) q.set('workspace_id', workspaceId)
  if (runId) q.set('run_id', runId)
  const query = q.toString()
  return `/bff/briefings/${date}/screening-log${query ? `?${query}` : ''}`
}

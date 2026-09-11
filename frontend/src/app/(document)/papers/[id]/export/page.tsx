import { runScope } from '@/app/(sidebar)/briefing/scope'
import { runContext } from '@/app/(sidebar)/papers/[id]/sections'
import { forPage } from '@/lib/bff/core/page'
import { isUuid } from '@/lib/bff/core/validate'
import { papers } from '@/lib/bff/papers/service'
import { workspaces } from '@/lib/bff/workspaces/service'
import { getLang, getT } from '@/lib/i18n-server'
import { paperHref } from '@/lib/papers/href'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { DocumentToolbar } from './document-toolbar'
import { PageFurniture, PaperDocument } from './paper-document'

/**
 * The paper's printable record — the paper page laid out as a document:
 * A4, running heads, page numbers, the abstract open, every definition
 * in full. Opened in its own tab from the masthead's "Export PDF" link, it
 * calls the browser's print dialog as soon as the fonts are in, and the
 * reader saves the dialog's output as a PDF. Nothing is generated on the
 * server: the browser is the typesetter, which keeps the image free of a
 * headless Chrome or a TeX, and prints the KaTeX and the fonts the app
 * already ships. On screen the same page previews as a sheet on a grey
 * ground with a toolbar (document-toolbar.tsx) to re-open the dialog.
 *
 * `?run=` means what it means on the page: the paper as that run read it,
 * resolved through the same `runContext`, so a record exported from a
 * briefing prints the briefing's decision and score. A run that does not
 * resolve prints the paper as it stands today.
 *
 * The tab's title is the paper's: Chrome names the saved PDF after it.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  const result = isUuid(id) ? await forPage(papers.get(id)) : null
  return { title: result ? result.paper.title : 'Paper' }
}

export default async function PaperExportPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ run?: string }>
}) {
  const [{ id }, { run }, t, lang] = await Promise.all([params, searchParams, getT(), getLang()])
  if (!isUuid(id)) notFound()
  const runId = runScope(run)

  const [result, ctx] = await Promise.all([
    forPage(papers.get(id, runId)),
    runId ? runContext(id, runId, lang) : null,
  ])
  if (!result) notFound()
  const paper = ctx ? ctx.paper : result.paper

  // The domain names the record in its running foot. Decoration: a
  // workspace read that fails leaves the foot to the date alone.
  const domain =
    ctx?.run.workspace_name ??
    (await workspaces
      .get(paper.workspace_id)
      .then((ws) => ws?.name ?? null)
      .catch(() => null))

  const exportedAt = new Date().toISOString()

  return (
    <>
      <DocumentToolbar backHref={paperHref(id, { runId: ctx?.run.id })} />
      <PageFurniture paper={paper} domain={domain} exportedAt={exportedAt} t={t} lang={lang} />
      <main className="doc-sheet">
        <PaperDocument paper={paper} domain={domain} exportedAt={exportedAt} t={t} lang={lang} />
      </main>
    </>
  )
}

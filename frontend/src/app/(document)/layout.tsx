import '@/styles/document.css'

/**
 * The document group: pages that are printed, not browsed. No sidebar, no
 * navbar — the root layout's fonts and tokens only, plus document.css, a
 * paged stylesheet (A4, running heads, page numbers) that the browser's
 * print dialog turns into a PDF. On screen the same page previews as a
 * sheet on a grey ground, with a toolbar that re-opens the dialog.
 */
export default function DocumentLayout({ children }: { children: React.ReactNode }) {
  return <div className="doc-stage">{children}</div>
}

import clsx from 'clsx'
import { Fragment, memo, type ReactNode } from 'react'
import Markdown, { type Components, type Options } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remend from 'remend'

/**
 * Model-written markdown (chat answers, screening notes, rationales), rendered
 * in the app's own type: no typography plugin, every element mapped to design
 * tokens. Raw HTML is dropped (`skipHtml`) and unsafe URL schemes are blanked
 * by react-markdown's default URL transform, so nothing the model writes can
 * execute or load remote content.
 *
 * No hooks and no 'use client' — renders from server pages and client
 * transcripts alike.
 */

// Key stats (percentages, multipliers, deltas) render in mono so they read as
// measurements, matching how numbers appear everywhere else in the app
// (docs/design.md → Type → Figures).
const STAT_RE = /(\d[\d,.]*%|\d+(?:\.\d+)?x|\(±?\+?\d+\))/g

// Private-use char appended to the source while streaming. It always ends the
// last text node, so swapping it for <Caret/> puts the caret at the end of
// whatever block the model is currently writing — a list item, a table cell,
// a code block — with no positional CSS. A space precedes it so it never
// touches a closing `_` and stops it from closing; that space is stripped
// again on render.
const CARET = ''
const CARET_TAIL = / ?$/

// `singleTilde: false` — scientific prose writes "~5% to ~10%", which default
// GFM would read as strikethrough.
const REMARK_PLUGINS: NonNullable<Options['remarkPlugins']> = [[remarkGfm, { singleTilde: false }]]

function Caret() {
  return (
    <span className="text-accent animate-pulse" aria-hidden="true">
      ▍
    </span>
  )
}

/** Strip the caret sentinel, wrap stats in mono, then append the caret element. */
function renderString(s: string, stats: boolean): ReactNode[] {
  const caret = s.endsWith(CARET)
  const body = caret ? s.replace(CARET_TAIL, '') : s
  const parts = stats ? body.split(STAT_RE) : [body]
  const out: ReactNode[] = parts.map((part, i) =>
    i % 2 === 1 ? (
      <span key={i} className="text-foreground font-mono font-medium tabular-nums">
        {part}
      </span>
    ) : (
      part
    ),
  )
  // Stable key so the pulse animation survives re-renders as text grows.
  if (caret) out.push(<Caret key="caret" />)
  return out
}

/** String children get the stat/caret pass; element children handle their own text. */
function inline(children: ReactNode, stats: boolean): ReactNode {
  if (typeof children === 'string') return renderString(children, stats)
  if (Array.isArray(children)) {
    return children.map((child, i) =>
      typeof child === 'string' ? <Fragment key={i}>{renderString(child, stats)}</Fragment> : child,
    )
  }
  return children
}

// Model headings become section labels: in a transcript the user's question is
// already the heading, and a full-size h3 mid-answer would outrank it.
function buildComponents(stats: boolean): Components {
  const Heading = ({ children }: { children?: ReactNode }) => (
    <h4 className="text-foreground pt-1 text-[11px] font-semibold tracking-[0.18em] uppercase">
      {inline(children, stats)}
    </h4>
  )
  return {
    p: ({ children }) => <p>{inline(children, stats)}</p>,
    h1: Heading,
    h2: Heading,
    h3: Heading,
    h4: Heading,
    h5: Heading,
    h6: Heading,
    ul: ({ children }) => (
      <ul className="marker:text-muted-foreground list-disc space-y-1 pl-4">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="marker:text-muted-foreground list-decimal space-y-1 pl-4 marker:font-mono marker:tabular-nums">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="pl-0.5 [&>ol]:mt-1 [&>ul]:mt-1">{inline(children, stats)}</li>
    ),
    strong: ({ children }) => (
      <strong className="text-foreground font-semibold">{inline(children, stats)}</strong>
    ),
    em: ({ children }) => <em className="italic">{inline(children, stats)}</em>,
    del: ({ children }) => <del className="line-through">{inline(children, stats)}</del>,
    // react-markdown blanks unsafe schemes (javascript:, data:…) before we see
    // them, so an empty href means "not a link".
    a: ({ href, children }) =>
      href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-700 underline underline-offset-2 hover:text-blue-800"
        >
          {inline(children, false)}
        </a>
      ) : (
        <span>{inline(children, false)}</span>
      ),
    code: ({ children }) => (
      <code className="bg-foreground/5 rounded-xs px-1 py-px font-mono text-[0.9em]">
        {inline(children, false)}
      </code>
    ),
    pre: ({ children }) => (
      <pre className="bg-foreground/3 border-line-soft overflow-x-auto rounded-sm border p-3 font-mono text-xs leading-normal whitespace-pre-wrap [&_code]:bg-transparent [&_code]:p-0">
        {children}
      </pre>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-line text-muted-foreground border-l-2 pl-3">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="border-line-soft my-3" />,
    table: ({ children }) => (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border-line text-foreground border-b py-1 pr-3 text-left align-bottom font-semibold">
        {inline(children, stats)}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-line-soft border-b py-1 pr-3 align-top">{inline(children, stats)}</td>
    ),
  }
}

// Built once: react-markdown re-parses when the components object changes.
const COMPONENTS_WITH_STATS = buildComponents(true)
const COMPONENTS_PLAIN = buildComponents(false)

/**
 * While streaming, close whatever markers the model is mid-way through
 * (`remend`) and append the caret sentinel. Trailing whitespace goes first so
 * the caret stays on the current block rather than jumping to an empty one. A
 * just-closed code fence or a table row gets a blank line instead: appended to
 * the fence the sentinel would reopen it, and after a row's last `|` it would
 * be an extra cell that GFM drops.
 */
function streamingSource(text: string): string {
  const mended = remend(text, { linkMode: 'text-only' }).replace(/\s+$/, '')
  const ownLine = mended.endsWith('```') || mended.endsWith('|')
  return ownLine ? `${mended}\n\n${CARET}` : `${mended} ${CARET}`
}

export const AnswerMarkdown = memo(function AnswerMarkdown({
  text,
  streaming = false,
  stats = true,
  className,
}: {
  text: string
  /** In-flight: repair unterminated markdown and show the caret. */
  streaming?: boolean
  /** Render figures (94.0%, 3.2x, (+12)) in mono per the design rule. */
  stats?: boolean
  /** Size and ink for the surface, e.g. `text-sm text-foreground/75`. */
  className?: string
}) {
  const source = streaming ? streamingSource(text) : text
  return (
    <div className={clsx('min-w-0 space-y-2 leading-relaxed break-words', className)}>
      <Markdown
        remarkPlugins={REMARK_PLUGINS}
        components={stats ? COMPONENTS_WITH_STATS : COMPONENTS_PLAIN}
        skipHtml
        disallowedElements={['img']}
        unwrapDisallowed
      >
        {source}
      </Markdown>
    </div>
  )
})

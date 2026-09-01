import type { VisualCitation } from '@/lib/bff/chat/schema'
import {
  extractCitationMarkers,
  holdBackOpenMarker,
  matchCitations,
  PLACEHOLDER_RE,
  type CitationRef,
} from '@/lib/chat/citation-markers'
import { fmt, type T } from '@/lib/i18n'
import { CheckCircleIcon } from '@heroicons/react/16/solid'
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
 * Chat answers can opt into citation chips: the model's inline
 * `[Page N, Fig X, box_2d: […], quote: "…"]` markers (which the backend parses
 * but leaves in the text) become `p. N · Fig X` chips tied to the structured
 * `visual_citations`.
 *
 * No hooks and no 'use client' — renders from server pages and client
 * transcripts alike; chrome strings arrive through the `t` prop.
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

// Streamed words resolve out of a soft blur. The span stays inline, so filter
// and opacity apply without disturbing line boxes; whitespace rides between
// spans as bare text so nothing is swallowed and keys stay put as text grows.
const UNVEIL = 'animate-unveil motion-reduce:animate-none'

const IDENTITY: T = (s) => s

interface RenderOpts {
  /** Render figures (94.0%, 3.2x, (+12)) in mono per the design rule. */
  stats: boolean
  /** Wrap each word in an unveiling span (streamed answers). */
  unveil: boolean
  /** Show the caret at the end of the block being written. */
  caret: boolean
}

/** Per-render citation context, threaded through the renderers as a closure. */
interface CiteCtx {
  refs: CitationRef[]
  matches: (VisualCitation | null)[]
  anchor?: string
  t: T
}

function Caret() {
  return (
    <span className="text-accent animate-pulse" aria-hidden="true">
      ▍
    </span>
  )
}

const CHIP_CLASS =
  // Left margin only, so trailing punctuation hugs the chip.
  'bg-foreground/6 ml-0.5 inline-flex items-baseline gap-1 rounded-sm px-1.5 py-px align-baseline font-mono text-[10px] font-medium tracking-[0.04em] text-blue-700 tabular-nums'

/**
 * `p. 7 · Fig 4b`, with a tick once the backend has verified the quote in the
 * source. Links to the citation card when the surface renders one.
 */
function CitationChip({ cite, index, ctx }: { cite: CitationRef; index: number; ctx: CiteCtx }) {
  const { t, anchor } = ctx
  const verified = ctx.matches[index]?.verified_in_source === true
  const label = [fmt(t('p. {n}'), { n: cite.page }), cite.label].filter(Boolean).join(' · ')
  const body = (
    <>
      {label}
      {verified && (
        <>
          <CheckCircleIcon
            className="text-accent size-3 self-center"
            title={t('Verified in source')}
          />
          <span className="sr-only">{t('Verified in source')}</span>
        </>
      )}
    </>
  )
  return anchor ? (
    <a
      href={`#${anchor}-${index}`}
      title={cite.quote}
      className={clsx(CHIP_CLASS, 'hover:bg-accent/10')}
    >
      {body}
    </a>
  ) : (
    <span title={cite.quote} className={CHIP_CLASS}>
      {body}
    </span>
  )
}

/** Each word in its own animated span; the whitespace between stays bare. */
function unveilWords(s: string, keyPrefix: string): ReactNode[] {
  return s.split(/(\s+)/).map((piece, j) =>
    piece === '' ? null : /^\s+$/.test(piece) ? (
      piece
    ) : (
      <span key={`${keyPrefix}-${j}`} className={UNVEIL}>
        {piece}
      </span>
    ),
  )
}

/** Strip the caret sentinel, swap citation placeholders for chips, wrap stats in mono (and words, when unveiling), append the caret. */
function renderString(s: string, opts: RenderOpts, cite?: CiteCtx): ReactNode[] {
  const hasCaret = s.endsWith(CARET)
  const body = hasCaret ? s.replace(CARET_TAIL, '') : s
  const segments = cite ? body.split(PLACEHOLDER_RE) : [body]
  const out: ReactNode[] = []
  segments.forEach((segment, i) => {
    if (cite && i % 2 === 1) {
      const index = Number(segment)
      const ref = cite.refs[index]
      if (!ref) return
      // The chip unveils whole; splitting its label would fight the tick.
      const chip = <CitationChip cite={ref} index={index} ctx={cite} />
      out.push(
        opts.unveil ? (
          <span key={`cite-${i}`} className={UNVEIL}>
            {chip}
          </span>
        ) : (
          <Fragment key={`cite-${i}`}>{chip}</Fragment>
        ),
      )
      return
    }
    const parts = opts.stats ? segment.split(STAT_RE) : [segment]
    parts.forEach((part, j) => {
      if (j % 2 === 1) {
        out.push(
          <span
            key={`${i}-${j}`}
            className={clsx(
              'text-foreground font-mono font-medium tabular-nums',
              opts.unveil && UNVEIL,
            )}
          >
            {part}
          </span>,
        )
        return
      }
      out.push(
        opts.unveil ? (
          <Fragment key={`${i}-${j}`}>{unveilWords(part, `${i}-${j}`)}</Fragment>
        ) : (
          part
        ),
      )
    })
  })
  // Stable key so the pulse animation survives re-renders as text grows.
  if (hasCaret && opts.caret) out.push(<Caret key="caret" />)
  return out
}

/** String children get the chip/stat/caret pass; element children handle their own text. */
function inline(children: ReactNode, opts: RenderOpts, cite?: CiteCtx): ReactNode {
  if (typeof children === 'string') return renderString(children, opts, cite)
  if (Array.isArray(children)) {
    return children.map((child, i) =>
      typeof child === 'string' ? (
        <Fragment key={i}>{renderString(child, opts, cite)}</Fragment>
      ) : (
        child
      ),
    )
  }
  return children
}

// Model headings become section labels: in a transcript the user's question is
// already the heading, and a full-size h3 mid-answer would outrank it.
function buildComponents(opts: RenderOpts, cite?: CiteCtx): Components {
  const plain: RenderOpts = { ...opts, stats: false }
  const Heading = ({ children }: { children?: ReactNode }) => (
    <h4 className="text-foreground pt-1 text-[11px] font-semibold tracking-[0.18em] uppercase">
      {inline(children, opts, cite)}
    </h4>
  )
  return {
    p: ({ children }) => <p>{inline(children, opts, cite)}</p>,
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
      <li className="pl-0.5 [&>ol]:mt-1 [&>ul]:mt-1">{inline(children, opts, cite)}</li>
    ),
    strong: ({ children }) => (
      <strong className="text-foreground font-semibold">{inline(children, opts, cite)}</strong>
    ),
    em: ({ children }) => <em className="italic">{inline(children, opts, cite)}</em>,
    del: ({ children }) => <del className="line-through">{inline(children, opts, cite)}</del>,
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
          {inline(children, plain, cite)}
        </a>
      ) : (
        <span>{inline(children, plain, cite)}</span>
      ),
    code: ({ children }) => (
      <code className="bg-foreground/5 rounded-xs px-1 py-px font-mono text-[0.9em]">
        {inline(children, plain, cite)}
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
        {inline(children, opts, cite)}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-line-soft border-b py-1 pr-3 align-top">
        {inline(children, opts, cite)}
      </td>
    ),
  }
}

// react-markdown re-parses on every render regardless; the cache only saves
// rebuilding the closures (one entry per stats/unveil/caret combination, of
// which there are a handful). `memo` on AnswerMarkdown is what avoids
// re-renders. Chip-enabled renders build a map per render (the context is
// per turn), which costs nothing extra.
const componentCache = new Map<string, Components>()
function componentsFor(opts: RenderOpts): Components {
  const key = `${opts.stats}|${opts.unveil}|${opts.caret}`
  let components = componentCache.get(key)
  if (!components) {
    components = buildComponents(opts)
    componentCache.set(key, components)
  }
  return components
}

/**
 * While streaming, close whatever markers the model is mid-way through
 * (`remend`) and append the caret sentinel. Trailing whitespace goes first so
 * the caret stays on the current block rather than jumping to an empty one. A
 * just-closed code fence or a table row gets a blank line instead: appended to
 * the fence the sentinel would reopen it, and after a row's last `|` it would
 * be an extra cell that GFM drops.
 */
function streamingSource(text: string, caret: boolean): string {
  const mended = remend(text, { linkMode: 'text-only' }).replace(/\s+$/, '')
  if (!caret) return mended
  const ownLine = mended.endsWith('```') || mended.endsWith('|')
  return ownLine ? `${mended}\n\n${CARET}` : `${mended} ${CARET}`
}

export const AnswerMarkdown = memo(function AnswerMarkdown({
  text,
  streaming = false,
  stats = true,
  unveil = false,
  caret = true,
  className,
  citations,
  citationAnchor,
  t = IDENTITY,
}: {
  text: string
  /** In-flight: repair unterminated markdown and show the caret. */
  streaming?: boolean
  /** Render figures (94.0%, 3.2x, (+12)) in mono per the design rule. */
  stats?: boolean
  /** Streamed words resolve out of a blur as they arrive (the Ask console). */
  unveil?: boolean
  /** Show the caret while streaming; off when the unveil carries the motion. */
  caret?: boolean
  /** Size and ink for the surface, e.g. `text-sm text-foreground/75`. */
  className?: string
  /**
   * Render `[Page N, …]` markers as chips, matched to these structured
   * citations. Omit to leave markers as text; `[]` while they are still
   * streaming in (chips without ticks).
   */
  citations?: VisualCitation[]
  /** DOM id prefix of the citation cards (`${prefix}-${i}`); chips link to them. */
  citationAnchor?: string
  /** Chrome strings (`p. {n}`, `Verified in source`); identity when omitted. */
  t?: T
}) {
  // Hold back a half-arrived marker before remend sees it (it would strip the
  // bracket), then swap closed markers for placeholders that survive parsing.
  const extracted = citations
    ? extractCitationMarkers(streaming ? holdBackOpenMarker(text) : text)
    : null
  const refs = extracted?.refs ?? []
  let source = extracted ? extracted.text : text
  if (streaming) source = streamingSource(source, caret)
  const opts: RenderOpts = { stats, unveil, caret }
  const cite: CiteCtx | undefined =
    refs.length > 0
      ? { refs, matches: matchCitations(refs, citations ?? []), anchor: citationAnchor, t }
      : undefined
  const components = cite ? buildComponents(opts, cite) : componentsFor(opts)
  return (
    <div className={clsx('min-w-0 space-y-2 leading-relaxed break-words', className)}>
      <Markdown
        remarkPlugins={REMARK_PLUGINS}
        components={components}
        skipHtml
        disallowedElements={['img']}
        unwrapDisallowed
      >
        {source}
      </Markdown>
    </div>
  )
})

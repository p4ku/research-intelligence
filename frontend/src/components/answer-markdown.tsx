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
import 'katex/dist/katex.min.css'
import { Fragment, memo, type ReactNode } from 'react'
import Markdown, { type Components, type Options } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remend from 'remend'
import { Bone } from './skeleton'

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
// GFM would read as strikethrough. `remark-math` + `rehype-katex` turn the
// LaTeX the OCR step writes into the markdown ($…$ inline, $$…$$ display, per
// `ocr_providers/gemini_provider.py`) into typeset math instead of raw source.
const REMARK_PLUGINS: NonNullable<Options['remarkPlugins']> = [
  [remarkGfm, { singleTilde: false }],
  remarkMath,
]

// `throwOnError: false` degrades an unparseable formula to its red source text
// instead of blowing up the answer; `strict: false` accepts the loose LaTeX
// models write (unicode in \text{}, \newline, …). `trust: false` (the default)
// keeps \href and \includegraphics out.
const REHYPE_PLUGINS: NonNullable<Options['rehypePlugins']> = [
  [rehypeKatex, { throwOnError: false, strict: false, errorColor: 'var(--negative)' }],
]

// Delimiters the OCR prompt allows (ocr_providers/gemini_provider.py) but
// remark-math does not read: `\(…\)` inline and `\[…\]` display. It also only
// treats `$$…$$` as a display block when the formula sits on its own lines, so
// a one-line `$$…$$` — which is what models write — is squared up here too.
// Fenced code is masked out first, so LaTeX quoted as code stays source.
const FENCE = /^```[\s\S]*?^```/gm
const MASK = /\u{E001}(\d+)\u{E001}/gu
const PAREN_MATH = /\\\(([\s\S]+?)\\\)/g
const BRACKET_MATH = /\\\[([\s\S]+?)\\\]/g
const OWN_LINE_BRACKET = /^[ \t]*\\\[([\s\S]+?)\\\][ \t]*$/gm
const OWN_LINE_DISPLAY = /^[ \t]*\$\$[ \t]*(.+?)[ \t]*\$\$[ \t]*$/gm

/** `\[x\]` or `$$x$$` alone on a line → the blank-line-fenced display block. */
const displayBlock = (body: string) => `\n\n$$\n${body.trim()}\n$$\n\n`

function normalizeMath(text: string): string {
  // Plain `$…$` needs nothing; skipping the passes keeps streaming re-renders,
  // which run this on every token, off the regexes.
  if (!text.includes('\\(') && !text.includes('\\[') && !text.includes('$$')) return text
  const fences: string[] = []
  const masked = text.replace(FENCE, (block) => `\u{E001}${fences.push(block) - 1}\u{E001}`)
  const converted = masked
    .replace(OWN_LINE_BRACKET, (_m, body: string) => displayBlock(body))
    .replace(BRACKET_MATH, (_m, body: string) => `$$${body}$$`)
    .replace(PAREN_MATH, (_m, body: string) => `$${body}$`)
    .replace(OWN_LINE_DISPLAY, (_m, body: string) => displayBlock(body))
  return fences.length === 0
    ? converted
    : converted.replace(MASK, (_m, i: string) => fences[Number(i)])
}

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
    <span className="animate-pulse text-accent" aria-hidden="true">
      ▍
    </span>
  )
}

// Hook for the KaTeX rules in styles/tailwind.css. They live there rather than
// as utilities here because they have to out-specify katex.min.css, which Next
// loads after the app stylesheet.
const MATH_CLASS = 'answer-md'

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
            className="size-3 self-center text-accent"
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
              'font-mono font-medium text-foreground tabular-nums',
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

/**
 * String children get the chip/stat/caret pass; element children handle their
 * own text. A lone string is wrapped exactly as it would be inside an array:
 * mid-stream a paragraph's single text child becomes `[text, <strong>, text]`
 * the moment the model closes a `**bold**` (or writes `$x$`, or a citation
 * marker), and if the two paths nested their words differently, every word
 * already on screen would remount and re-run its unveil — the answer flickers.
 */
function inline(children: ReactNode, opts: RenderOpts, cite?: CiteCtx): ReactNode {
  const list = typeof children === 'string' ? [children] : children
  if (!Array.isArray(list)) return children
  return list.map((child, i) =>
    typeof child === 'string' ? (
      <Fragment key={i}>{renderString(child, opts, cite)}</Fragment>
    ) : (
      child
    ),
  )
}

// Model headings become section labels: in a transcript the user's question is
// already the heading, and a full-size h3 mid-answer would outrank it.
function buildComponents(opts: RenderOpts, cite?: CiteCtx): Components {
  const plain: RenderOpts = { ...opts, stats: false }
  const Heading = ({ children }: { children?: ReactNode }) => (
    <h4 className="pt-1 text-[11px] font-semibold tracking-[0.18em] text-foreground uppercase">
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
      <ul className="list-disc space-y-1 pl-4 marker:text-muted-foreground">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="list-decimal space-y-1 pl-4 marker:font-mono marker:text-muted-foreground marker:tabular-nums">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="pl-0.5 [&>ol]:mt-1 [&>ul]:mt-1">{inline(children, opts, cite)}</li>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-foreground">{inline(children, opts, cite)}</strong>
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
      <code className="rounded-xs bg-foreground/5 px-1 py-px font-mono text-[0.9em]">
        {inline(children, plain, cite)}
      </code>
    ),
    pre: ({ children }) => (
      <pre className="overflow-x-auto rounded-sm border border-line-soft bg-foreground/3 p-3 font-mono text-xs leading-normal whitespace-pre-wrap [&_code]:bg-transparent [&_code]:p-0">
        {children}
      </pre>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-line pl-3 text-muted-foreground">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-3 border-line-soft" />,
    table: ({ children }) => (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border-b border-line py-1 pr-3 text-left align-bottom font-semibold text-foreground">
        {inline(children, opts, cite)}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b border-line-soft py-1 pr-3 align-top">
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
 * A formula still being written is TeX source, and showing it only to swap it
 * for typeset math a moment later makes the line flash. So while the stream is
 * open, hold back the tail after an unpaired `$` — but only when it reads like
 * LaTeX (a backslash, a brace, a superscript) and is still short, so a lone `$`
 * in prose ("about $5 a run") never swallows the rest of the answer.
 */
const OPEN_MATH = /\$([^$\n]*)$/
const LOOKS_LATEX = /[\\{}^_]/

function holdBackOpenMath(text: string): string {
  // An odd number of `$$` means a display block is open; it spans lines, so it
  // is measured from the last one rather than by a line-bound match.
  if ((text.match(/\$\$/g)?.length ?? 0) % 2 === 1) {
    const at = text.lastIndexOf('$$')
    const body = text.slice(at + 2)
    if (body.length <= 400 && (body.trim() === '' || LOOKS_LATEX.test(body)))
      return text.slice(0, at)
    return text
  }
  if ((text.match(/\$/g)?.length ?? 0) % 2 === 0) return text
  const open = OPEN_MATH.exec(text)
  if (!open) return text
  const body = open[1]
  return body.length <= 120 && LOOKS_LATEX.test(body) ? text.slice(0, open.index) : text
}

/**
 * While streaming, close whatever markers the model is mid-way through
 * (`remend`) and append the caret sentinel. Trailing whitespace goes first so
 * the caret stays on the current block rather than jumping to an empty one. A
 * just-closed code fence, table row or display formula gets a blank line
 * instead: appended to the fence the sentinel would reopen it, after a row's
 * last `|` it would be an extra cell that GFM drops, and on a closing `$$` it
 * would leave the formula unterminated.
 */
function streamingSource(text: string, caret: boolean): string {
  const mended = remend(holdBackOpenMath(text), { linkMode: 'text-only' }).replace(/\s+$/, '')
  if (!caret) return mended
  const ownLine = mended.endsWith('```') || mended.endsWith('|') || mended.endsWith('$$')
  return ownLine ? `${mended}\n\n${CARET}` : `${mended} ${CARET}`
}

// One root class for the loaded renderer and its skeleton (drift contract).
const ROOT_CLASS = 'min-w-0 space-y-2 leading-relaxed break-words'

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
  let source = normalizeMath(extracted ? extracted.text : text)
  if (streaming) source = streamingSource(source, caret)
  const opts: RenderOpts = { stats, unveil, caret }
  const cite: CiteCtx | undefined =
    refs.length > 0
      ? { refs, matches: matchCitations(refs, citations ?? []), anchor: citationAnchor, t }
      : undefined
  const components = cite ? buildComponents(opts, cite) : componentsFor(opts)
  return (
    <div
      data-shape="answer-markdown"
      data-state="loaded"
      className={clsx(ROOT_CLASS, MATH_CLASS, className)}
    >
      <Markdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
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

/**
 * The prose loading state — for finished documents only (the dashboard brief).
 * Streaming chat answers keep ScanningLine + the caret; never skeleton them.
 */
export function AnswerMarkdownSkeleton({
  className,
  heading = false,
  paragraphs = [3, 2],
}: {
  className?: string
  /** Lead with a short heading-width bone. */
  heading?: boolean
  /** One entry per paragraph: its line count. */
  paragraphs?: number[]
}) {
  return (
    <div data-shape="answer-markdown" data-state="skeleton" className={clsx(ROOT_CLASS, className)}>
      {heading && (
        <div className="pt-1">
          <Bone.Text widths={['18ch']} />
        </div>
      )}
      {paragraphs.map((lines, i) => (
        <div key={i}>
          <Bone.Text lines={lines} />
        </div>
      ))}
    </div>
  )
}

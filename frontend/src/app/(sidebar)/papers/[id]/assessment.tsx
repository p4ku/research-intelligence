import { AnswerMarkdown, AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { Bone } from '@/components/skeleton'
import { fmt, type T } from '@/lib/i18n'
import type { Dimension, DimensionFacet } from '@/lib/papers/types'
import clsx from 'clsx'
import type { ReactNode } from 'react'

/**
 * The assessment: one article per definition, in the workspace's order, laid
 * out from what the definition emitted — its headline and band, the model's
 * justification, the sub-scores as facet rows (each with its assessment text
 * when the definition wrote one), the longer prose fields, the lists, the
 * quoted evidence, the short facts, and one quiet line of provenance. Nothing
 * here knows a definition by name, so a definition added in the admin renders
 * like the ones before it.
 *
 * Every article carries an id (`definitionAnchor`) for the rail's bars to link
 * to. AssessmentFrame / DefinitionFrame own the layout; Assessment fills them
 * with data and AssessmentSkeleton with bones.
 */

/** The article id a rail bar links to. */
export function definitionAnchor(d: Pick<Dimension, 'key' | 'extraction_id'>): string {
  return `dimension-${d.key}${d.extraction_id ? `-${d.extraction_id.slice(0, 8)}` : ''}`
}

const PROSE = 'max-w-[76ch] text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300'
const SMALL_PROSE = 'max-w-[76ch] text-sm leading-relaxed text-zinc-600 dark:text-zinc-400'
const H4 = 'text-sm font-semibold text-zinc-950 dark:text-white'
const FIGURE = 'font-mono font-medium text-zinc-950 tabular-nums dark:text-white'
const META = 'text-xs text-zinc-400 dark:text-zinc-500'

export function AssessmentFrame({
  state = 'loaded',
  children,
}: {
  state?: 'loaded' | 'skeleton'
  children: ReactNode
}) {
  return (
    <div data-shape="assessment" data-state={state} className="border-t border-line">
      {children}
    </div>
  )
}

export function DefinitionFrame({
  id,
  name,
  band,
  value,
  children,
}: {
  id?: string
  name: ReactNode
  band?: ReactNode
  value: ReactNode
  children: ReactNode
}) {
  return (
    <article id={id} data-row="definition" className="scroll-mt-6 border-b border-line-soft py-6">
      <header className="flex items-baseline gap-2.5">
        <h3 className="text-[17px] font-semibold tracking-[-0.005em] text-zinc-950 dark:text-white">
          {name}
        </h3>
        {band}
        <span className={clsx(FIGURE, 'ml-auto shrink-0 text-[22px] leading-none')}>{value}</span>
      </header>
      <div className="mt-3.5 space-y-4">{children}</div>
    </article>
  )
}

function Band({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-sm bg-foreground/6 px-1.5 py-px text-xs font-medium text-zinc-600 dark:text-zinc-300">
      {children}
    </span>
  )
}

/** Integers plain, otherwise at most two decimals — the same reading as the rail. */
function shownNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : (Math.round(n * 100) / 100).toString()
}

/** The headline as the row shows it: the number, or the raw string when there is none. */
function shownValue(d: Dimension): ReactNode {
  if (d.value === null) return <span className="text-zinc-500 dark:text-zinc-400">{d.raw}</span>
  return (
    <>
      {shownNumber(d.value)}
      {d.max !== null && d.max !== 100 && (
        <span className="text-[11px] font-normal text-zinc-400">/{d.max}</span>
      )}
    </>
  )
}

/** The model sometimes quotes its quote; one pair of marks is ours. */
function unquote(quote: string): string {
  return quote
    .trim()
    .replace(/^[“"„']+/, '')
    .replace(/[”"“']+$/, '')
}

/** "google/gemini-3.8-flash" → "Gemini 3.8 Flash". */
function modelName(id: string): string {
  return (id.split('/').pop() ?? id).replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function FacetRowFrame({
  name,
  fill,
  value,
  text,
}: {
  name: ReactNode
  /** The 3px track's fill; omitted when the facet has no scale (figure only). */
  fill?: ReactNode | false
  value: ReactNode
  text?: ReactNode
}) {
  return (
    <li
      className={clsx(
        'grid items-center gap-x-3.5 gap-y-1',
        fill === undefined || fill === false
          ? 'grid-cols-[minmax(0,1fr)_44px]'
          : 'grid-cols-[minmax(0,1fr)_44px] sm:grid-cols-[200px_minmax(0,1fr)_44px]',
      )}
    >
      <span className="text-sm text-zinc-700 dark:text-zinc-200">{name}</span>
      {fill !== undefined && fill !== false && (
        <span className="col-span-full block h-[3px] w-full overflow-hidden bg-line-soft sm:col-span-1">
          {fill}
        </span>
      )}
      <span className={clsx(FIGURE, 'col-start-2 row-start-1 text-right text-sm sm:col-start-3')}>
        {value}
      </span>
      {text && <div className="col-span-full">{text}</div>}
    </li>
  )
}

function FacetRow({ facet: f }: { facet: DimensionFacet }) {
  const hasBar = f.max !== null && f.max > 0
  const pct = hasBar ? Math.max(0, Math.min(1, f.value / f.max!)) : 0
  return (
    <FacetRowFrame
      name={f.name}
      fill={
        hasBar && (
          <span
            className="block h-full w-full origin-left bg-accent"
            style={{ transform: `scaleX(${pct})` }}
          />
        )
      }
      value={shownNumber(f.value)}
      text={f.text && <p className={SMALL_PROSE}>{f.text}</p>}
    />
  )
}

function Definition({ dimension: d, t }: { dimension: Dimension; t: T }) {
  const conf =
    typeof d.confidence === 'number'
      ? d.confidence <= 1
        ? `${Math.round(d.confidence * 100)}%`
        : String(d.confidence)
      : null
  const review =
    d.review_required || d.validation_status === 'warn' || d.validation_status === 'fail'
  const meta: ReactNode[] = []
  if (conf) meta.push(fmt(t('Confidence {n}'), { n: conf }))
  if (d.model) meta.push(modelName(d.model))
  if (review)
    meta.push(
      <span className="font-medium text-zinc-500 dark:text-zinc-400">{t('Needs review')}</span>,
    )

  return (
    <DefinitionFrame
      id={definitionAnchor(d)}
      name={d.name}
      band={d.band && <Band>{d.band}</Band>}
      value={shownValue(d)}
    >
      {d.rationale ? (
        <AnswerMarkdown text={d.rationale} className={PROSE} />
      ) : (
        <p className="text-sm text-zinc-400">{t('No rationale recorded.')}</p>
      )}
      {d.facets && d.facets.length > 0 && (
        <ul className="space-y-2.5">
          {d.facets.map((f) => (
            <FacetRow key={f.key} facet={f} />
          ))}
        </ul>
      )}
      {d.texts?.map((field) => (
        <div key={field.key}>
          <h4 className={H4}>{field.name}</h4>
          <AnswerMarkdown text={String(field.value)} className={clsx(PROSE, 'mt-1.5')} />
        </div>
      ))}
      {d.lists?.map((list) => (
        <div key={list.key}>
          <h4 className={H4}>{list.name}</h4>
          <ul className="mt-1.5 max-w-[76ch] space-y-1.5">
            {list.items.map((item, i) => (
              <li
                key={i}
                className="relative pl-4 text-sm leading-relaxed text-zinc-700 before:absolute before:top-[0.8em] before:left-0 before:h-px before:w-[7px] before:bg-zinc-500 before:content-[''] dark:text-zinc-300"
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {d.evidence?.map((quote, i) => (
        <blockquote
          key={i}
          className="max-w-[72ch] border-l-2 border-line pl-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400"
        >
          “{unquote(quote)}”
        </blockquote>
      ))}
      {d.facts && d.facts.length > 0 && (
        <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-5 gap-y-1.5 text-sm">
          {d.facts.map((fact) => (
            <div key={fact.key} className="contents">
              <dt className="font-medium text-zinc-950 dark:text-white">{fact.name}</dt>
              <dd className="text-zinc-600 dark:text-zinc-400">
                {typeof fact.value === 'boolean' ? (fact.value ? t('Yes') : t('No')) : fact.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {meta.length > 0 && (
        <p className={META}>
          {meta.map((part, i) => (
            <span key={i}>
              {i > 0 && <span aria-hidden="true"> · </span>}
              {part}
            </span>
          ))}
        </p>
      )}
    </DefinitionFrame>
  )
}

export function Assessment({ dimensions, t }: { dimensions: Dimension[]; t: T }) {
  if (dimensions.length === 0) {
    return (
      <AssessmentFrame>
        <p className="py-4 text-sm text-zinc-400">{t('Not scored yet')}</p>
      </AssessmentFrame>
    )
  }
  return (
    <AssessmentFrame>
      {dimensions.map((d) => (
        <Definition key={d.key + (d.extraction_id ?? '')} dimension={d} t={t} />
      ))}
    </AssessmentFrame>
  )
}

/* -------------------------------- Skeleton --------------------------------- */

/** How much of a definition the bones reserve: lines of lead, facet rows, and so on. */
export interface DefinitionShape {
  band?: boolean
  /** Lines of the justification paragraph; 0 reserves the "No rationale recorded." line instead. */
  lead: number
  /** One entry per facet row: the lines of assessment text under it (0 for none). */
  facets?: number[]
  /** Lines per prose field. */
  texts?: number[]
  /** Items in one list, with its heading. */
  list?: number
  quotes?: number
  facts?: number
  meta?: boolean
}

// The live domain's shape: a paragraph of justification, three sub-scores, a
// prose field and a short list, seven times. A domain with fewer definitions
// sees the column shorten on load.
export const ASSESSMENT_SHAPE: DefinitionShape[] = Array.from({ length: 7 }, () => ({
  band: true,
  lead: 4,
  facets: [0, 0, 0],
  texts: [3],
  list: 3,
  meta: true,
}))

export function DefinitionSkeleton({ shape }: { shape: DefinitionShape }) {
  return (
    <DefinitionFrame
      name={<Bone.Text widths={['12ch']} />}
      band={shape.band && <Bone.Chip width={56} />}
      value={<Bone.Number digits={4} />}
    >
      {shape.lead > 0 ? (
        <AnswerMarkdownSkeleton className={PROSE} paragraphs={[shape.lead]} />
      ) : (
        <p className="text-sm">
          <Bone.Text widths={['20ch']} />
        </p>
      )}
      {shape.facets?.length ? (
        <ul className="space-y-2.5">
          {shape.facets.map((lines, i) => (
            <FacetRowFrame
              key={i}
              name={<Bone.Text widths={['10ch', '13ch', '9ch'].slice(i % 3)} />}
              fill={null}
              value={<Bone.Number digits={2} />}
              text={
                lines > 0 && (
                  <p className={SMALL_PROSE}>
                    <Bone.Text lines={lines} widths={['100%', '54%']} />
                  </p>
                )
              }
            />
          ))}
        </ul>
      ) : null}
      {shape.texts?.map((lines, i) => (
        <div key={i}>
          <h4 className={H4}>
            <Bone.Text widths={['16ch']} />
          </h4>
          <AnswerMarkdownSkeleton className={clsx(PROSE, 'mt-1.5')} paragraphs={[lines]} />
        </div>
      ))}
      {shape.list ? (
        <div>
          <h4 className={H4}>
            <Bone.Text widths={['14ch']} />
          </h4>
          <ul className="mt-1.5 max-w-[76ch] space-y-1.5">
            {Array.from({ length: shape.list }, (_, i) => (
              <li key={i} className="pl-4 text-sm leading-relaxed">
                <Bone.Text widths={['84%', '62%', '90%'].slice(i % 3)} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {Array.from({ length: shape.quotes ?? 0 }, (_, i) => (
        <blockquote
          key={i}
          className="max-w-[72ch] border-l-2 border-line pl-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400"
        >
          <Bone.Text widths={['46%']} />
        </blockquote>
      ))}
      {shape.facts ? (
        <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-5 gap-y-1.5 text-sm">
          {Array.from({ length: shape.facts }, (_, i) => (
            <div key={i} className="contents">
              <dt>
                <Bone.Text widths={['18ch']} />
              </dt>
              <dd>
                <Bone.Text widths={['4ch']} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {shape.meta && (
        <p className={META}>
          <Bone.Text widths={['28ch']} />
        </p>
      )}
    </DefinitionFrame>
  )
}

export function AssessmentSkeleton({ shapes = ASSESSMENT_SHAPE }: { shapes?: DefinitionShape[] }) {
  return (
    <AssessmentFrame state="skeleton">
      {shapes.map((shape, i) => (
        <DefinitionSkeleton key={i} shape={shape} />
      ))}
    </AssessmentFrame>
  )
}

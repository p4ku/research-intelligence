import { AnswerMarkdown, AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { SectionLabel } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { fmt, formatNumber, type Lang, type T } from '@/lib/i18n'
import { dimensionLabel } from '@/lib/papers/dimension-label'
import type { Dimension, DimensionFacet, DimensionField } from '@/lib/papers/types'
import clsx from 'clsx'
import type { ReactNode } from 'react'

/**
 * The assessment: one article per definition, in the workspace's order, laid
 * out from what the definition emitted — its name as a section label (the
 * teal-square eyebrow every section of the app opens with; there is no
 * "Assessment" heading above them, each definition is a section of the
 * record in its own right, a peer of Summary), its headline and band, the model's
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

export function isProse(text: string | null | undefined): boolean {
  if (!text) return false
  const trimmed = text.trim()
  if (trimmed === '' || trimmed === '—') return false
  return trimmed.length > 25 || trimmed.split(/\s+/).length > 3 || trimmed.includes('\n')
}

const PROSE =
  'max-w-[76ch] text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300 break-words text-pretty'
const SMALL_PROSE =
  'max-w-[76ch] text-sm leading-relaxed text-zinc-600 dark:text-zinc-400 break-words text-pretty'
const H4 = 'text-sm font-semibold text-zinc-950 dark:text-white'
const FIGURE = 'font-mono font-medium text-zinc-950 tabular-nums dark:text-white'

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
    <article
      id={id}
      data-row="definition"
      className="scroll-mt-6 border-b border-line-soft py-6 last:border-b-0"
    >
      <header className="flex items-baseline gap-2.5">
        <SectionLabel>{name}</SectionLabel>
        {band}
        {value != null && value !== '' ? (
          <span className={clsx(FIGURE, 'ml-auto shrink-0 text-[22px] leading-none')}>{value}</span>
        ) : null}
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
function shownNumber(n: number | null | undefined, lang: Lang): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  return formatNumber(n, lang, undefined, 2)
}

/** The headline as the row shows it: the number, or the raw string when there is none (excluding prose sentences). */
function shownValue(d: Dimension, lang: Lang): ReactNode {
  if (d.value === null) {
    if (!d.raw || d.raw === '—' || d.raw.trim() === '' || isProse(d.raw)) return null
    return <span className="text-zinc-500 dark:text-zinc-400">{d.raw}</span>
  }
  return (
    <>
      {shownNumber(d.value, lang)}
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

function FacetRowFrame({
  name,
  fill,
  value,
  text,
}: {
  name: ReactNode
  /** The 3px track's fill; omitted when the facet has no scale (figure only). */
  fill?: ReactNode
  value: ReactNode
  text?: ReactNode
}) {
  return (
    <li
      className={clsx(
        'grid items-center gap-x-3 gap-y-1',
        fill === undefined || fill === false
          ? 'grid-cols-[minmax(0,1fr)_44px]'
          : 'grid-cols-[minmax(0,1fr)_44px] sm:grid-cols-[minmax(0,1fr)_140px_44px]',
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

interface SchemaProperty {
  title?: string
  description?: string
  maximum?: number
  minimum?: number
  type?: string
}

export function getSchemaProperty(
  schema: Record<string, unknown> | null | undefined,
  key: string,
): SchemaProperty | null {
  if (!schema || typeof schema !== 'object') return null
  const properties = schema.properties as Record<string, unknown> | undefined
  if (!properties || typeof properties !== 'object') return null

  // 1. Direct key match
  let prop = properties[key] as Record<string, unknown> | undefined

  // 2. Case and underscore insensitive match
  if (!prop) {
    const cleanKey = key.toLowerCase().replace(/[-_ ]/g, '')
    for (const [k, v] of Object.entries(properties)) {
      if (k.toLowerCase().replace(/[-_ ]/g, '') === cleanKey) {
        prop = v as Record<string, unknown>
        break
      }
    }
  }

  // 3. Match without _score or _assessment suffix
  if (!prop) {
    const cleanBase = key
      .toLowerCase()
      .replace(/[-_ ]/g, '')
      .replace(/(score|assessment)$/, '')
    if (cleanBase) {
      for (const [k, v] of Object.entries(properties)) {
        const kBase = k
          .toLowerCase()
          .replace(/[-_ ]/g, '')
          .replace(/(score|assessment)$/, '')
        if (kBase === cleanBase) {
          prop = v as Record<string, unknown>
          break
        }
      }
    }
  }

  if (!prop || typeof prop !== 'object') return null

  const title = typeof prop.title === 'string' && prop.title.trim() ? prop.title.trim() : undefined
  const description =
    typeof prop.description === 'string' && prop.description.trim()
      ? prop.description.trim()
      : undefined
  const type = typeof prop.type === 'string' ? prop.type : undefined

  let maximum: number | undefined
  if (typeof prop.maximum === 'number' && Number.isFinite(prop.maximum)) {
    maximum = prop.maximum
  } else if (prop.properties && typeof prop.properties === 'object') {
    const nestedScore = (prop.properties as Record<string, unknown>).score as
      | Record<string, unknown>
      | undefined
    if (
      nestedScore &&
      typeof nestedScore.maximum === 'number' &&
      Number.isFinite(nestedScore.maximum)
    ) {
      maximum = nestedScore.maximum
    }
  }

  return { title, description, maximum, type }
}

interface UnpackedField {
  key?: string
  name: string
  description?: string | null
  value: string | boolean | number | null
  band?: string | null
  evidence?: string[] | null
  score?: number | null
  is_dict: boolean
}

function unpackField(field: DimensionField): UnpackedField {
  let band = field.band ?? null
  let value: string | boolean | number | null =
    typeof field.value === 'object' && field.value !== null ? '' : field.value
  let evidence = field.evidence ?? null
  let score = field.score ?? null
  let isDict = Boolean(field.is_dict || field.type === 'dict')

  // 1. Structured dictionary sent directly from backend
  if (field.dict_value && typeof field.dict_value === 'object') {
    isDict = true
    const parsed = field.dict_value as Record<string, unknown>
    if (!band && parsed.band) band = String(parsed.band).trim()
    if (score == null && parsed.score != null) {
      const s = Number(parsed.score)
      if (Number.isFinite(s)) score = s
    }
    if (value === '' || value == null) {
      const ins =
        parsed.insight ??
        parsed.rationale ??
        parsed.reasoning ??
        parsed.explanation ??
        parsed.text ??
        parsed.summary
      if (ins != null) value = String(ins).trim()
    }

    if (!evidence && Array.isArray(parsed.evidence)) {
      evidence = (parsed.evidence as unknown[])
        .map((e) =>
          typeof e === 'object' && e !== null && 'quote' in e
            ? String((e as { quote: unknown }).quote)
            : String(e),
        )
        .map((s) => s.trim())
        .filter(Boolean)
    }
  } else if (
    typeof value === 'string' &&
    value.trim().startsWith('{') &&
    value.trim().endsWith('}')
  ) {
    // 2. Safe JSON parse for stringified dictionary (without corrupting regex swaps)
    try {
      const parsed = JSON.parse(value.trim())
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        isDict = true
        if (!band && parsed.band) band = String(parsed.band).trim()
        if (score == null && parsed.score != null) {
          const s = Number(parsed.score)
          if (Number.isFinite(s)) score = s
        }
        const ins =
          parsed.insight ??
          parsed.rationale ??
          parsed.reasoning ??
          parsed.explanation ??
          parsed.text ??
          parsed.summary
        if (ins != null) value = String(ins).trim()
        else value = ''

        if (!evidence && Array.isArray(parsed.evidence)) {
          evidence = (parsed.evidence as unknown[])
            .map((e) =>
              typeof e === 'object' && e !== null && 'quote' in e
                ? String((e as { quote: unknown }).quote)
                : String(e),
            )
            .map((s) => s.trim())
            .filter(Boolean)
        }
      }
    } catch {
      // Leave unparsed if not valid JSON
    }
  }

  if (isDict && !band && field.band) band = field.band
  if (isDict && !evidence && field.evidence) evidence = field.evidence

  return { name: field.name, value, band, evidence, score, is_dict: isDict }
}

interface SubMeasure {
  key: string
  name: string
  description?: string | null
  band?: string | null
  value?: number | null
  max?: number | null
  text?: string | null
  evidence?: string[] | null
  is_dict: boolean
}

function subMeasureKey(key: string, name?: string): string {
  return (name || key)
    .toLowerCase()
    .replace(/[-_ ]/g, '')
    .replace(/_?score$/, '')
}

function resolveSubMeasures(
  facets?: DimensionFacet[] | null,
  texts?: DimensionField[] | null,
  fallbackMax: number | null = 100,
  responseSchema?: Record<string, unknown> | null,
): { subMeasures: SubMeasure[]; generalTexts: UnpackedField[] } {
  const subMeasures: SubMeasure[] = []
  const seenBases = new Map<string, SubMeasure>()
  const generalTexts: UnpackedField[] = []

  // 1. Process facets first
  for (const f of facets ?? []) {
    const schemaProp = getSchemaProperty(responseSchema, f.key)
    let displayName = schemaProp?.title || f.name
    let description = schemaProp?.description || null
    const maxVal = schemaProp?.maximum ?? f.max ?? fallbackMax

    const fKeyNorm = (f.key || '').toLowerCase().replace(/[-_ ]/g, '')
    const fNameNorm = displayName.toLowerCase().replace(/[-_ ]/g, '')
    if (fKeyNorm === 'coretechnology' || fNameNorm === 'coretechnology') {
      displayName = 'Technology being Assessed'
      description = null
    } else if (
      description &&
      (description.toLowerCase() === 'the technology being assessed.' ||
        description.toLowerCase() === 'the technology being assessed')
    ) {
      description = null
    }

    const norm = subMeasureKey(f.key, f.name)
    if (seenBases.has(norm)) {
      const existing = seenBases.get(norm)!
      if (!existing.band && f.band) existing.band = f.band
      if (existing.value == null && f.value != null) existing.value = f.value
      if (!existing.text && f.text) existing.text = f.text
      if (!existing.description && description) existing.description = description
      const fEv = (f as { evidence?: string[] }).evidence
      if ((!existing.evidence || existing.evidence.length === 0) && fEv?.length) {
        existing.evidence = fEv
      }
      continue
    }

    const sub: SubMeasure = {
      key: f.key,
      name: displayName,
      description,
      band: f.band ?? null,
      value: f.value,
      max: maxVal,
      text: f.text ?? null,
      evidence: (f as { evidence?: string[] }).evidence ?? null,
      is_dict: Boolean(f.band || (f as { evidence?: string[] }).evidence),
    }
    seenBases.set(norm, sub)
    subMeasures.push(sub)
  }

  // 2. Process texts
  for (const rawField of texts ?? []) {
    const field = unpackField(rawField)
    if (!field.value && !field.band && (!field.evidence || field.evidence.length === 0)) continue

    const schemaProp = getSchemaProperty(responseSchema, rawField.key)
    let displayName = schemaProp?.title || field.name
    let description = schemaProp?.description || null

    const kNorm = (rawField.key || '').toLowerCase().replace(/[-_ ]/g, '')
    const dNorm = displayName.toLowerCase().replace(/[-_ ]/g, '')
    if (kNorm === 'coretechnology' || dNorm === 'coretechnology') {
      displayName = 'Technology being Assessed'
      description = null
    } else if (
      description &&
      (description.toLowerCase() === 'the technology being assessed.' ||
        description.toLowerCase() === 'the technology being assessed')
    ) {
      description = null
    }

    const norm = subMeasureKey(rawField.key, field.name)
    if (seenBases.has(norm)) {
      const existing = seenBases.get(norm)!
      if (!existing.band && field.band) existing.band = field.band
      if (existing.value == null && field.score != null) existing.value = field.score
      if (!existing.text && typeof field.value === 'string' && field.value) {
        existing.text = field.value
      }
      if (!existing.description && description) existing.description = description
      if ((!existing.evidence || existing.evidence.length === 0) && field.evidence?.length) {
        existing.evidence = field.evidence
      }
      if (field.is_dict) existing.is_dict = true
    } else if (field.is_dict) {
      const sub: SubMeasure = {
        key: rawField.key,
        name: displayName,
        description,
        band: field.band ?? null,
        value: field.score ?? null,
        max: schemaProp?.maximum ?? fallbackMax ?? 100,
        text: typeof field.value === 'string' && field.value ? field.value : null,
        evidence: field.evidence ?? null,
        is_dict: true,
      }
      seenBases.set(norm, sub)
      subMeasures.push(sub)
    } else {
      generalTexts.push({
        ...field,
        key: rawField.key,
        name: displayName,
        description,
      })
    }
  }

  return { subMeasures, generalTexts }
}

function SubMeasureRow({ sub, t, lang }: { sub: SubMeasure; t: T; lang: Lang }) {
  const hasBar =
    typeof sub.max === 'number' &&
    sub.max > 0 &&
    typeof sub.value === 'number' &&
    Number.isFinite(sub.value)
  const pct =
    hasBar && typeof sub.value === 'number' && typeof sub.max === 'number'
      ? Math.max(0, Math.min(1, sub.value / sub.max))
      : 0
  const hasProse = Boolean(sub.text)
  const hasEvidence = Boolean(sub.evidence && sub.evidence.length > 0)
  const isRich = hasProse || hasEvidence || sub.is_dict

  return (
    <div
      data-type={sub.is_dict ? 'submetric-dict' : undefined}
      data-submetric={sub.key}
      className={clsx(
        'space-y-3',
        isRich &&
          'rounded-lg border border-line-soft/70 bg-transparent p-4 transition-colors hover:border-line sm:p-4.5',
      )}
    >
      <div
        className={clsx(
          'grid items-center gap-x-3 gap-y-1',
          hasBar
            ? 'grid-cols-[minmax(0,1fr)_44px] sm:grid-cols-[minmax(0,1fr)_140px_44px]'
            : 'grid-cols-[minmax(0,1fr)_44px]',
        )}
      >
        <div className="flex min-w-0 items-center">
          <span
            title={dimensionLabel(sub.name, t)}
            className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100"
          >
            {dimensionLabel(sub.name, t)}
          </span>
        </div>

        {hasBar && (
          <span className="col-span-full block h-[3px] w-full overflow-hidden rounded-full bg-line-soft/70 sm:col-span-1">
            <span
              className="block h-full w-full origin-left rounded-full bg-accent"
              style={{ transform: `scaleX(${pct})` }}
            />
          </span>
        )}

        <div className="col-start-2 row-start-1 text-right sm:col-start-3">
          <span className={clsx(FIGURE, 'text-sm')}>{shownNumber(sub.value, lang)}</span>
          {sub.is_dict && sub.value != null && (
            <span className="sr-only">
              {fmt(t('Sub-score: {n}'), { n: shownNumber(sub.value, lang) })}
            </span>
          )}
        </div>
      </div>

      {sub.text && (
        <AnswerMarkdown
          text={sub.text}
          className={clsx(SMALL_PROSE, 'mt-1 text-zinc-700 dark:text-zinc-300')}
        />
      )}

      {/* Evidence quotes: preserved in backend JSON for LLM faithfulness, hidden on frontend UI */}
      {hasEvidence && (
        <div
          className="mt-2.5 hidden space-y-1.5 border-l-2 border-line-soft pl-3.5"
          data-slot="evidence"
          aria-hidden="true"
        >
          <span className="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase dark:text-zinc-500">
            {t('Evidence')}
          </span>
          {sub.evidence!.map((quote, i) => (
            <blockquote
              key={i}
              className="max-w-[72ch] text-[13px] leading-relaxed text-zinc-600 italic dark:text-zinc-400"
            >
              “{unquote(quote)}”
            </blockquote>
          ))}
        </div>
      )}
    </div>
  )
}

function Definition({ dimension: d, t, lang }: { dimension: Dimension; t: T; lang: Lang }) {
  const isTrl =
    d.is_trl || d.key.toLowerCase().includes('trl') || d.name.toLowerCase().includes('trl')

  const { subMeasures, generalTexts } = resolveSubMeasures(
    d.facets,
    d.texts,
    d.max,
    d.response_schema,
  )

  const visibleSubMeasures = subMeasures.filter((sub) => {
    const k = sub.key.toLowerCase()
    const n = sub.name.toLowerCase()
    if (
      isTrl &&
      (k === 'confidence' ||
        n === 'confidence' ||
        k === 'confidence_level' ||
        n === 'confidence level')
    ) {
      return false
    }
    return true
  })

  const visibleTexts = generalTexts.filter((field) => {
    const k = (field.key ?? '').toLowerCase()
    const n = field.name.toLowerCase()
    if (isTrl && (k.includes('confidence') || n.includes('confidence'))) return false
    if (k === 'confidence' || n === 'confidence') return false
    return true
  })

  const isInsight = (field: { key?: string | null; name: string }) => {
    const k = (field.key ?? '').toLowerCase().replace(/[-_ ]/g, '')
    const n = field.name.toLowerCase().replace(/[-_ ]/g, '')
    return k.includes('insight') || n.includes('insight')
  }

  const isSubMeasureDuplicate = (field: { key?: string | null; name: string }) => {
    const fk = (field.key ?? '')
      .toLowerCase()
      .replace(/[-_ ]/g, '')
      .replace(/_?score$/, '')
    const fn = field.name
      .toLowerCase()
      .replace(/[-_ ]/g, '')
      .replace(/_?score$/, '')
    return visibleSubMeasures.some((sub) => {
      const sk = sub.key
        .toLowerCase()
        .replace(/[-_ ]/g, '')
        .replace(/_?score$/, '')
      const sn = sub.name
        .toLowerCase()
        .replace(/[-_ ]/g, '')
        .replace(/_?score$/, '')
      return fk === sk || fn === sn || fk === sn || fn === sk
    })
  }

  const textInsights = visibleTexts
    .filter((field) => isInsight(field) && field.value != null && String(field.value).trim() !== '')
    .map((field) => ({
      key: field.key ?? field.name,
      value: String(field.value).trim(),
    }))

  const factInsights = (d.facts ?? [])
    .filter((fact) => isInsight(fact) && fact.value != null && String(fact.value).trim() !== '')
    .map((fact) => ({
      key: fact.key,
      value: String(fact.value).trim(),
    }))

  // A fact named after its own definition (`tldr` inside "TLDR") is the
  // definition's summary, not a row: it reads as the lead under the heading,
  // the way Research Metrics and Schwarz Fit open with their prose.
  const norm = (s: string) => s.toLowerCase().replace(/[-_ ]/g, '')
  const isSelfFact = (fact: { key: string; name: string }) => {
    const dk = norm(d.key)
    const dn = norm(d.name)
    const fk = norm(fact.key)
    const fn = norm(fact.name)
    return fk === dk || fn === dn || fk === dn || fn === dk
  }
  const selfProse =
    (d.facts ?? []).find(
      (fact) => isSelfFact(fact) && typeof fact.value === 'string' && fact.value.trim() !== '',
    )?.value ?? null
  const selfLead = typeof selfProse === 'string' ? selfProse.trim() : null

  const rawProse =
    d.value === null && d.raw && d.raw !== '—' && isProse(d.raw) ? d.raw.trim() : null
  const leadProse = d.rationale?.trim() || rawProse || selfLead
  const secondaryProse =
    d.rationale?.trim() && rawProse && rawProse !== d.rationale.trim() ? rawProse : null

  const allInsights = [...textInsights, ...factInsights]
  const topInsights = allInsights.filter(
    (field, idx) =>
      (!leadProse || leadProse !== field.value) &&
      allInsights.findIndex((other) => other.value === field.value) === idx,
  )

  const remainingTexts = visibleTexts
    .filter((field) => !isInsight(field))
    .filter((field) => {
      const v = String(field.value ?? '').trim()
      if (!v) return false
      if (leadProse && v === leadProse) return false
      if (secondaryProse && v === secondaryProse) return false
      return true
    })

  const visibleFacts = (d.facts ?? [])
    .filter((fact) => {
      const k = fact.key.toLowerCase()
      const n = fact.name.toLowerCase()
      if (isTrl && (k.includes('confidence') || n.includes('confidence'))) return false
      if (k === 'confidence' || n === 'confidence') return false
      if (isInsight(fact)) return false
      if (isSubMeasureDuplicate(fact)) return false
      if (isSelfFact(fact)) return false
      const v = String(fact.value ?? '').trim()
      if (leadProse && v === leadProse) return false
      if (secondaryProse && v === secondaryProse) return false
      return true
    })
    .map((fact) => {
      const kNorm = (fact.key || '').toLowerCase().replace(/[-_ ]/g, '')
      const nNorm = fact.name.toLowerCase().replace(/[-_ ]/g, '')
      if (kNorm === 'coretechnology' || nNorm === 'coretechnology') {
        return { ...fact, name: 'Technology being Assessed' }
      }
      return fact
    })

  return (
    <DefinitionFrame
      id={definitionAnchor(d)}
      name={dimensionLabel(d.name, t)}
      band={d.band && <Band>{d.band}</Band>}
      value={shownValue(d, lang)}
    >
      {leadProse ? <AnswerMarkdown text={leadProse} className={PROSE} /> : null}
      {secondaryProse ? <AnswerMarkdown text={secondaryProse} className={PROSE} /> : null}
      {selfLead && selfLead !== leadProse && selfLead !== secondaryProse ? (
        <AnswerMarkdown text={selfLead} className={PROSE} />
      ) : null}

      {/* Top insight prose boxes (e.g. "Research Quality Insight", "Schwarz Fit Insight") without subtitle */}
      {topInsights.map((field) => (
        <AnswerMarkdown key={field.key} text={field.value} className={PROSE} />
      ))}

      {/* Sub-metrics / Secondary metrics with progress bar, score, prose & evidence */}
      {visibleSubMeasures.length > 0 && (
        <div className="space-y-3">
          {visibleSubMeasures.map((sub) => (
            <SubMeasureRow key={sub.key} sub={sub} t={t} lang={lang} />
          ))}
        </div>
      )}

      {/* Remaining dimension-level prose texts (e.g. "Hardware Architecture Notes", "Core technology") */}
      {remainingTexts.map((field) => (
        <div key={field.name} className="space-y-1.5">
          <h4 className={H4}>{dimensionLabel(field.name, t)}</h4>
          {field.description && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">{field.description}</p>
          )}
          <AnswerMarkdown text={String(field.value)} className={clsx(PROSE, 'mt-1.5')} />
        </div>
      ))}

      {/* Lists */}
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

      {/* Top-level evidence (deduplicated against sub-measure evidence quotes; hidden on frontend) */}
      {d.evidence
        ?.filter((quote) => {
          const unq = unquote(quote).trim()
          return !visibleSubMeasures.some((sub) =>
            sub.evidence?.some((ev) => unquote(ev).trim() === unq),
          )
        })
        .map((quote, i) => (
          <blockquote
            key={i}
            className="hidden max-w-[72ch] border-l-2 border-line pl-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400"
            data-slot="top-level-evidence"
            aria-hidden="true"
          >
            “{unquote(quote)}”
          </blockquote>
        ))}

      {/* Facts */}
      {visibleFacts.length > 0 && (
        <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-5 gap-y-1.5 text-sm">
          {visibleFacts.map((fact) => (
            <div key={fact.key} className="contents">
              <dt className="font-medium text-zinc-950 dark:text-white">
                {dimensionLabel(fact.name, t)}
              </dt>
              <dd className="text-zinc-600 dark:text-zinc-400">
                {typeof fact.value === 'boolean'
                  ? fact.value
                    ? t('Yes')
                    : t('No')
                  : typeof fact.value === 'object' && fact.value !== null
                    ? JSON.stringify(fact.value)
                    : String(fact.value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </DefinitionFrame>
  )
}

export function Assessment({
  dimensions,
  t,
  lang = 'en',
}: {
  dimensions: Dimension[]
  t: T
  lang?: Lang
}) {
  const visibleDimensions = (dimensions ?? [])
    .filter((d) => !d.is_risk_and_affiliation && !d.key.includes('risk_and_affiliation'))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))

  if (visibleDimensions.length === 0) {
    return (
      <AssessmentFrame>
        <p className="py-4 text-sm text-zinc-400">{t('Not scored yet')}</p>
      </AssessmentFrame>
    )
  }
  return (
    <AssessmentFrame>
      {visibleDimensions.map((d) => (
        <Definition key={d.key + (d.extraction_id ?? '')} dimension={d} t={t} lang={lang} />
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
      ) : null}
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

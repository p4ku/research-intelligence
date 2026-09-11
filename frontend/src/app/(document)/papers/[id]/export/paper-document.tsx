import { getFlagSortOrder, unpackFlag } from '@/app/(sidebar)/papers/[id]/affiliation-flags'
import {
  definitionView,
  isProse,
  type DefinitionView,
  type SubMeasure,
} from '@/app/(sidebar)/papers/[id]/assessment'
import { isDisplayableRailDimension, radarAxes } from '@/app/(sidebar)/papers/[id]/score-rail'
import { AnswerMarkdown } from '@/components/answer-markdown'
import { RadarChart } from '@/components/charts'
import { fmt, formatDate, type Lang, type T } from '@/lib/i18n'
import { dimensionLabel, dimensionShortName } from '@/lib/papers/dimension-label'
import { arxivIdOf, doiOf } from '@/lib/papers/map'
import { formatMeasure, formatScore, trimTitle } from '@/lib/papers/select'
import type { Dimension, ScoredPaper } from '@/lib/papers/types'
import clsx from 'clsx'
import type { ReactNode } from 'react'

/**
 * The paper as a document. The same record the page shows, in reading
 * order, composed for paper rather than for a scrolling column: a masthead
 * (brand and domain on the first line, the title, the authors, the
 * provenance), a glance band (the Schwarz Score, one bar per scaled
 * definition, the radar), the record's metadata (affiliations, funding,
 * the compliance verdicts), the abstract in full — on paper nothing folds
 * — the pipeline's summary, then the assessment definition by definition
 * exactly as `definitionView` resolves it for the page, and a colophon.
 *
 * Every rule here is a class in document.css; the markup carries no
 * utilities, so the sheet reads the same in the preview and in print and
 * the stylesheet can be tuned without touching the tree. Sans for the
 * furniture (Switzer, the app's own), a serif for the long prose — the
 * app's rule reserves serif for long-form reading, and a printed record is
 * exactly that — and Plex Mono for every figure.
 */

interface DocProps {
  paper: ScoredPaper
  /** The domain the record belongs to; null when it could not be read. */
  domain: string | null
  /** ISO time the export was made — the foot of every page carries it. */
  exportedAt: string
  t: T
  lang: Lang
}

const BRAND = 'Research Intelligence'

/** A string as CSS `content` accepts it: quoted, with quotes, backslashes and line breaks escaped. */
function cssString(s: string): string {
  return `"${s
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/[\r\n]+/g, ' ')}"`
}

/**
 * The running heads and feet, as CSS page-margin boxes: the brand and the
 * title along the top of every page but the first (which carries both in
 * full), the domain and export date at the foot, and "n / N" at the right.
 * Written as a style element because the page context cannot read the
 * DOM — the strings have to be in the stylesheet itself.
 */
export function PageFurniture({ paper, domain, exportedAt, t, lang }: DocProps) {
  const foot = [domain, fmt(t('Exported {date}'), { date: formatDate(exportedAt, lang) })]
    .filter(Boolean)
    .join(' · ')
  const css = `
@page {
  @top-left { content: ${cssString(BRAND)}; }
  @top-right { content: ${cssString(trimTitle(paper.title, 72))}; }
  @bottom-left { content: ${cssString(foot)}; }
  @bottom-right { content: counter(page) " / " counter(pages); }
}
@page :first {
  @top-left { content: none; }
  @top-right { content: none; }
}
`
  return <style>{css}</style>
}

/* -------------------------------- Masthead -------------------------------- */

function authorsOf(paper: ScoredPaper): string {
  return Array.isArray(paper.authors)
    ? paper.authors.join(', ') || paper.authors_raw
    : paper.authors || paper.authors_raw || ''
}

function Masthead({ paper, domain, exportedAt, t, lang }: DocProps) {
  const arxiv = paper.arxiv_id ?? (paper.source_url ? arxivIdOf(paper.source_url) : null)
  const doi = paper.doi ?? (paper.source_url ? doiOf(paper.source_url) : null)
  return (
    <header className="doc-masthead">
      <div className="doc-brandline">
        <span className="doc-brand">
          <span aria-hidden="true" className="doc-square" />
          {BRAND}
        </span>
        <span className="doc-context">
          {domain && <span>{domain}</span>}
          <span>{fmt(t('Exported {date}'), { date: formatDate(exportedAt, lang) })}</span>
        </span>
      </div>

      <p className="doc-meta">
        {paper.is_benchmark && (
          <span className="doc-meta-mark">
            {paper.evaluation_label
              ? `${t('Benchmark Control')} (${paper.evaluation_label === 'passed' ? t('Passed') : t('Rejected')})`
              : t('Benchmark Control')}
          </span>
        )}
        <span>{paper.source}</span>
        <span>
          {paper.published_date
            ? fmt(t('Published {date}'), { date: formatDate(paper.published_date, lang) })
            : fmt(t('Ingested {date}'), { date: formatDate(paper.created_at, lang) })}
        </span>
        {arxiv && <span className="doc-mono">arXiv {arxiv}</span>}
        {doi && <span className="doc-mono">DOI {doi}</span>}
      </p>
      <h1 className="doc-title">{paper.title}</h1>
      <p className="doc-authors">{authorsOf(paper)}</p>
    </header>
  )
}

/* --------------------------------- Glance --------------------------------- */

/** The headline figure a scaled definition prints, with its scale when that is not the 0–100 default. */
function Figure({ d, lang, size }: { d: Dimension; lang: Lang; size: 'lg' | 'sm' }) {
  const hasScale = d.value !== null && d.max !== null && d.max > 0
  return (
    <span className={clsx('doc-figure', size === 'lg' ? 'doc-figure-lg' : 'doc-figure-sm')}>
      {formatMeasure(d.value, d.max, lang)}
      {hasScale && d.max !== 100 && <span className="doc-figure-max">/{d.max}</span>}
    </span>
  )
}

function Track({ pct }: { pct: number }) {
  return (
    <span className="doc-track" aria-hidden="true">
      <span style={{ width: `${Math.round(Math.max(0, Math.min(1, pct)) * 100)}%` }} />
    </span>
  )
}

function Glance({ paper, dimensions, t, lang }: DocProps & { dimensions: Dimension[] }) {
  const scaled = dimensions.filter(isDisplayableRailDimension)
  const axes = radarAxes(scaled, t, lang)
  const score = formatScore(paper.signal_score)
  return (
    <section className={clsx('doc-glance', axes.length >= 3 && 'doc-glance-radar')}>
      <div className="doc-score">
        <span className="doc-score-figure">{score}</span>
        <span className="doc-score-label">{t('Schwarz Score')}</span>
      </div>
      {scaled.length > 0 && (
        <table className="doc-bars">
          <tbody>
            {scaled.map((d) => {
              const hasBar = d.value !== null && d.max !== null && d.max > 0
              return (
                <tr key={d.key + (d.extraction_id ?? '')}>
                  <td className="doc-bars-name">{dimensionShortName(d, t)}</td>
                  <td className="doc-bars-track">{hasBar && <Track pct={d.value! / d.max!} />}</td>
                  <td className="doc-bars-figure">
                    <Figure d={d} lang={lang} size="sm" />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {axes.length >= 3 && (
        <figure className="doc-radar">
          <RadarChart axes={axes} color="var(--doc-accent)" size={250} valueLabels />
        </figure>
      )}
    </section>
  )
}

/* --------------------------------- Record --------------------------------- */

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="doc-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** The metadata card's rows, as a definition list: affiliations, contacts, artifact, funding, compliance. */
function Record({ paper, t }: DocProps) {
  const risk = paper.risk_and_affiliation
  if (!risk) return null
  const affiliations = risk.affiliations ?? []
  const contacts = risk.author_contacts ?? []
  const funding = risk.funding_entities ?? []
  const flags = [...(risk.flags ?? [])].sort((a, b) => getFlagSortOrder(a) - getFlagSortOrder(b))
  const hasRisk = typeof risk.risk_score === 'number'
  if (
    !affiliations.length &&
    !contacts.length &&
    !funding.length &&
    !risk.codebase_artifact_link &&
    !flags.length &&
    !hasRisk
  ) {
    return null
  }
  return (
    <dl className="doc-record">
      {affiliations.length > 0 && <Row label={t('Affiliations')}>{affiliations.join(' · ')}</Row>}
      {contacts.length > 0 && (
        <Row label={t('Contacts')}>
          <span className="doc-mono">{contacts.join(', ')}</span>
        </Row>
      )}
      {risk.codebase_artifact_link && (
        <Row label={t('Artifact Repository')}>
          <a href={risk.codebase_artifact_link} className="doc-mono doc-url">
            {risk.codebase_artifact_link}
          </a>
        </Row>
      )}
      {funding.length > 0 && <Row label={t('Funding')}>{funding.join('; ')}</Row>}
      {(flags.length > 0 || hasRisk) && (
        <Row label={t('Compliance')}>
          <span className="doc-chips">
            {flags.map((raw) => {
              const flag = unpackFlag(raw, t)
              return (
                <span
                  key={raw.key}
                  className={clsx(
                    'doc-chip',
                    flag.status === 'safe' && 'doc-chip-safe',
                    flag.status === 'warn' && 'doc-chip-warn',
                  )}
                >
                  <b>{flag.label}:</b> {flag.value}
                </span>
              )
            })}
            {hasRisk && (
              <span className="doc-chip">
                <b>{t('Risk Score:')}</b> {risk.risk_score}/100
                {risk.risk_score_assessment && ` (${risk.risk_score_assessment})`}
              </span>
            )}
          </span>
        </Row>
      )}
    </dl>
  )
}

/* ------------------------------- Assessment ------------------------------- */

function Label({ children, size = 'sm' }: { children: ReactNode; size?: 'sm' | 'lg' }) {
  return (
    <h2 className={clsx('doc-label', size === 'lg' && 'doc-label-lg')}>
      <span aria-hidden="true" className="doc-square" />
      {children}
    </h2>
  )
}

/** The headline as the page's header shows it: the figure, or the raw string when there is none (never a sentence). */
function Headline({ d, lang }: { d: Dimension; lang: Lang }) {
  if (d.value === null) {
    if (!d.raw || d.raw === '—' || d.raw.trim() === '' || isProse(d.raw)) return null
    return <span className="doc-figure doc-figure-lg doc-figure-raw">{d.raw}</span>
  }
  return <Figure d={d} lang={lang} size="lg" />
}

function SubMeasureBlock({ sub, t, lang }: { sub: SubMeasure; t: T; lang: Lang }) {
  const hasBar =
    typeof sub.max === 'number' &&
    sub.max > 0 &&
    typeof sub.value === 'number' &&
    Number.isFinite(sub.value)
  return (
    <div className="doc-sub">
      <div className={clsx('doc-sub-head', hasBar && 'doc-sub-head-bar')}>
        <span className="doc-sub-name">{dimensionLabel(sub.name, t)}</span>
        {hasBar && <Track pct={(sub.value as number) / (sub.max as number)} />}
        <span className="doc-figure doc-figure-sm">{formatMeasure(sub.value, sub.max, lang)}</span>
      </div>
      {sub.text && <AnswerMarkdown text={sub.text} className="doc-prose doc-prose-sm" />}
    </div>
  )
}

function Definition({
  d,
  view,
  t,
  lang,
}: {
  d: Dimension
  view: DefinitionView
  t: T
  lang: Lang
}) {
  const { leadProse, secondaryProse, selfLead, topInsights, subMeasures, texts, facts } = view
  return (
    <section className="doc-definition">
      <header className="doc-definition-head">
        <Label size="lg">{dimensionLabel(d.name, t)}</Label>
        {d.band && <span className="doc-band">{d.band}</span>}
        <Headline d={d} lang={lang} />
      </header>

      {leadProse && <AnswerMarkdown text={leadProse} className="doc-prose" />}
      {secondaryProse && <AnswerMarkdown text={secondaryProse} className="doc-prose" />}
      {selfLead && selfLead !== leadProse && selfLead !== secondaryProse && (
        <AnswerMarkdown text={selfLead} className="doc-prose" />
      )}
      {topInsights.map((field) => (
        <AnswerMarkdown key={field.key} text={field.value} className="doc-prose" />
      ))}

      {subMeasures.length > 0 && (
        <div className="doc-subs">
          {subMeasures.map((sub) => (
            <SubMeasureBlock key={sub.key} sub={sub} t={t} lang={lang} />
          ))}
        </div>
      )}

      {texts.map((field) => (
        <div key={field.name} className="doc-field">
          <h3 className="doc-h3">{dimensionLabel(field.name, t)}</h3>
          {field.description && <p className="doc-field-note">{field.description}</p>}
          <AnswerMarkdown text={String(field.value)} className="doc-prose" />
        </div>
      ))}

      {d.lists?.map((list) => (
        <div key={list.key} className="doc-field">
          <h3 className="doc-h3">{list.name}</h3>
          <ul className="doc-list">
            {list.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      ))}

      {facts.length > 0 && (
        <dl className="doc-facts">
          {facts.map((fact) => (
            <div key={fact.key} className="doc-row">
              <dt>{dimensionLabel(fact.name, t)}</dt>
              <dd>
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
    </section>
  )
}

/* -------------------------------- Colophon -------------------------------- */

function Colophon({ paper, t, lang }: DocProps) {
  return (
    <footer className="doc-colophon">
      <dl>
        {paper.source_url && (
          <Row label={t('Source')}>
            <a href={paper.source_url} className="doc-mono doc-url">
              {paper.source_url}
            </a>
          </Row>
        )}
        <Row label={t('Ingested')}>{formatDate(paper.created_at, lang)}</Row>
        <Row label={t('Run')}>
          {paper.pipeline_run_name ?? (
            <span className="doc-mono">{(paper.pipeline_run_id ?? '').slice(0, 8)}</span>
          )}
        </Row>
      </dl>
    </footer>
  )
}

/* -------------------------------- Document -------------------------------- */

export function PaperDocument(props: DocProps) {
  const { paper, t } = props
  // The page's order: every definition but Risk & Affiliation, which the
  // record's rows carry instead.
  const dimensions = (paper.dimensions ?? [])
    .filter((d) => !d.is_risk_and_affiliation && !d.key.includes('risk_and_affiliation'))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))

  return (
    <article className="doc" data-shape="paper-document">
      <Masthead {...props} />
      <Glance {...props} dimensions={dimensions} />
      <Record {...props} />

      {paper.abstract && (
        <section className="doc-section">
          <Label>{t('Abstract')}</Label>
          <p className="doc-prose">{paper.abstract}</p>
        </section>
      )}

      {paper.summary && (
        <section className="doc-section">
          <Label>{t('Summary')}</Label>
          <p className="doc-prose">{paper.summary}</p>
        </section>
      )}

      <section className="doc-assessment">
        {dimensions.length === 0 ? (
          <p className="doc-empty">{t('Not scored yet')}</p>
        ) : (
          dimensions.map((d) => (
            <Definition
              key={d.key + (d.extraction_id ?? '')}
              d={d}
              view={definitionView(d)}
              t={t}
              lang={props.lang}
            />
          ))
        )}
      </section>

      <Colophon {...props} />
    </article>
  )
}

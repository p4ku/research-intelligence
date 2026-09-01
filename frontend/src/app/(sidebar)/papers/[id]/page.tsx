import { AnswerMarkdown } from '@/components/answer-markdown'
import { RadarChart } from '@/components/charts'
import {
  Breadcrumbs,
  Card,
  ScoreRow,
  ScreeningPill,
  SectionLabel,
  SignalScore,
  TrlBadge,
  dimensionRadarAxes,
} from '@/components/scanner-ui'
import { ScoreVariables } from '@/components/score-variables'
import { SignalLedger } from '@/components/signal-ledger'
import { forPage } from '@/lib/bff/core/page'
import { papers } from '@/lib/bff/papers/service'
import { formatDate } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import { trlDimension } from '@/lib/papers/select'
import { ledgerInputs } from '@/lib/papers/signal-formula'
import type { Dimension } from '@/lib/papers/types'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { PaperChat } from './paper-chat'

export const dynamic = 'force-dynamic'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  const result = await forPage(papers.get(id))
  return { title: result ? result.paper.title : 'Paper' }
}

export default async function PaperDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const result = await forPage(papers.get(id))
  if (!result) notFound()
  const { paper } = result

  const t = await getT()
  const lang = await getLang()
  const trl = trlDimension(paper)
  const radarAxes = dimensionRadarAxes(paper.dimensions)
  const details = paper.signal_score_details
  const ledger = ledgerInputs(details?.code_snippet, details?.variables, paper.signal_score)

  return (
    <div className="mx-auto max-w-7xl">
      <Breadcrumbs items={[{ label: t('Papers'), href: '/papers' }, { label: paper.title }]} />

      <div className="mt-8 grid items-start gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="min-w-0 space-y-8">
          {/* Header */}
          <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <ScreeningPill status={paper.screening_status} t={t} />
                <span className="text-xs text-zinc-400">·</span>
                <span className="text-xs text-zinc-400">{paper.source}</span>
                <span className="text-xs text-zinc-400">·</span>
                <span className="text-xs text-zinc-400">{formatDate(paper.created_at, lang)}</span>
                {paper.arxiv_id && (
                  <>
                    <span className="text-xs text-zinc-400">·</span>
                    <span className="font-mono text-xs text-zinc-400">arXiv:{paper.arxiv_id}</span>
                  </>
                )}
              </div>
              <h1 className="mt-2 text-2xl leading-tight font-semibold tracking-tight text-zinc-950 dark:text-white">
                {paper.title}
              </h1>
              <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                {paper.authors.join(', ') || paper.authors_raw}
              </p>
            </div>
          </div>

          {/* Signal score: a ledger when the breakdown provably applies, else the inputs. */}
          {ledger && details ? (
            <Card>
              <SignalLedger
                inputs={ledger}
                heading={
                  <>
                    <SectionLabel>{t('Signal score')}</SectionLabel>
                    <p className="mt-1 text-xs text-zinc-400">
                      {t('What the score is made of — and what would move it.')}
                    </p>
                  </>
                }
              />
              <ScoreVariables
                mode="compact"
                variables={details.variables}
                code={details.code_snippet}
                t={t}
                className="border-line-soft mt-4 border-t pt-3"
              />
            </Card>
          ) : (
            <Card className="flex flex-wrap items-start gap-6">
              <SignalScore score={paper.signal_score} size="lg" />
              <div className="min-w-0 flex-1">
                <SectionLabel>{t('Signal score')}</SectionLabel>
                <p className="mt-1 text-xs text-zinc-400">
                  {paper.signal_score === null
                    ? t('Not scored yet')
                    : t('Composite score from the workspace’s signal-score formula.')}
                </p>
                {details?.error && (
                  <p className="mt-2 inline-flex rounded-sm bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-300">
                    {t('Formula error')}: {details.error}
                  </p>
                )}
                {details && (
                  <ScoreVariables
                    variables={details.variables}
                    code={details.code_snippet}
                    t={t}
                    className="mt-3"
                  />
                )}
              </div>
            </Card>
          )}

          {/* Dimensions + profile */}
          <div className="grid gap-6 lg:grid-cols-5">
            <Card className={radarAxes.length >= 3 ? 'lg:col-span-3' : 'lg:col-span-5'}>
              <div className="flex items-center justify-between">
                <SectionLabel>{t('Dimensions')}</SectionLabel>
                {trl?.value !== null && trl?.value !== undefined && (
                  <TrlBadge trl={trl.value} t={t} />
                )}
              </div>
              <p className="mt-1 text-xs text-zinc-400">
                {t(
                  'Scored by the workspace’s extraction definitions, with the model’s rationale where it gave one.',
                )}
              </p>
              <div className="mt-5 space-y-5">
                {paper.dimensions.map((d) => (
                  <ScoreRow
                    key={d.key + (d.extraction_id ?? '')}
                    label={d.name}
                    value={d.value}
                    max={d.max}
                    raw={d.raw}
                    rationale={d.rationale}
                    evidence={d.evidence}
                    meta={<DimensionTags dimension={d} t={t} />}
                  />
                ))}
                {paper.dimensions.length === 0 && (
                  <p className="text-sm text-zinc-400">{t('Not scored yet')}</p>
                )}
              </div>
            </Card>

            {radarAxes.length >= 3 && (
              <Card className="flex flex-col lg:col-span-2">
                <SectionLabel>{t('Profile')}</SectionLabel>
                <div className="flex flex-1 items-center justify-center">
                  <RadarChart axes={radarAxes} color="var(--accent)" size={240} className="mt-2" />
                </div>
              </Card>
            )}
          </div>

          {/* Screening */}
          <Card>
            <div className="flex items-center justify-between">
              <SectionLabel>{t('Screening')}</SectionLabel>
              <ScreeningPill status={paper.screening_status} t={t} />
            </div>
            {paper.screening_reasoning ? (
              <AnswerMarkdown
                text={paper.screening_reasoning}
                className="mt-2 text-sm text-zinc-700 dark:text-zinc-300"
              />
            ) : (
              <p className="mt-2 text-sm leading-relaxed text-zinc-400">
                {t('No screening notes.')}
              </p>
            )}
          </Card>

          {/* Abstract */}
          <Card>
            <SectionLabel>{t('Abstract')}</SectionLabel>
            <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              {paper.abstract}
            </p>
          </Card>

          {/* Files */}
          <Card>
            <SectionLabel>{t('Files')}</SectionLabel>
            <div className="mt-3 space-y-2 text-sm">
              {paper.pdf_url && (
                <a
                  href={paper.pdf_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {paper.arxiv_id ? t('Open on arXiv') : t('Open DOI')} ↗
                </a>
              )}
              {paper.pdf_key && <FileKey label={t('Stored PDF')} value={paper.pdf_key} />}
              {paper.markdown_key && (
                <FileKey label={t('Stored markdown')} value={paper.markdown_key} />
              )}
              {(paper.pdf_key || paper.markdown_key) && (
                <p className="text-xs text-zinc-400">
                  {t('No file endpoint yet — storage key shown for reference.')}
                </p>
              )}
              {!paper.pdf_url && !paper.pdf_key && !paper.markdown_key && (
                <p className="text-zinc-400">{t('No files recorded.')}</p>
              )}
            </div>
          </Card>
        </div>

        {/* Ask the paper: a scoped conversation alongside the record. */}
        <PaperChat paper={paper} />
      </div>
    </div>
  )
}

function DimensionTags({ dimension: d, t }: { dimension: Dimension; t: (s: string) => string }) {
  const tags: string[] = []
  if (typeof d.confidence === 'number') {
    tags.push(
      `${t('Confidence')} ${d.confidence <= 1 ? `${Math.round(d.confidence * 100)}%` : d.confidence}`,
    )
  }
  if (d.review_required || d.validation_status === 'warn' || d.validation_status === 'fail') {
    tags.push(t('Needs review'))
  }
  if (tags.length === 0) return null
  return (
    <span className="hidden gap-1.5 sm:inline-flex">
      {tags.map((tag) => (
        <span
          key={tag}
          className="bg-foreground/6 rounded-sm px-1.5 py-0.5 font-mono text-[10px] text-zinc-500 dark:text-zinc-400"
        >
          {tag}
        </span>
      ))}
    </span>
  )
}

function FileKey({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
      <code className="min-w-0 truncate font-mono text-xs text-zinc-600 dark:text-zinc-300">
        {value}
      </code>
    </div>
  )
}

import { AnswerMarkdown, AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { PaperCard, PaperCardSkeleton } from '@/components/paper-card'
import {
  Card,
  DimensionsFrame,
  PageHeader,
  ScoreRow,
  ScoreRowSkeleton,
  SectionLabel,
  StatBand,
  StatBandSkeleton,
  StatTile,
  StatTileSkeleton,
} from '@/components/scanner-ui'
import { SignalLedger, SignalLedgerSkeleton } from '@/components/signal-ledger'
import { Skeleton } from '@/components/skeleton'
import { fixtureEditions } from '@/lib/bff/briefings/fixtures'
import { fixtureSessions } from '@/lib/bff/chat/fixtures'
import { fixtureSteps } from '@/lib/bff/component-runs/fixtures'
import { fixturePapers, fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { fixtureRunDetail, fixtureRuns } from '@/lib/bff/pipeline-runs/fixtures'
import type { T } from '@/lib/i18n'
import type { ReactNode } from 'react'
import { HistoryRailSkeleton } from '../../(sidebar)/ask/history-rail'
import { PaperPickerSkeleton } from '../../(sidebar)/ask/paper-picker'
import type { PaletteEntry } from '../../(sidebar)/ask/types'
import {
  ExclusionsTable,
  ExclusionsTableSkeleton,
} from '../../(sidebar)/briefing/[date]/run/exclusions-table'
import {
  EditionBrowser,
  EditionBrowserSkeleton,
  type BrowserEdition,
} from '../../(sidebar)/briefing/edition-browser'
import { RunPapers, RunPapersSkeleton } from '../../(sidebar)/dashboard/run-papers'
import {
  PaperHeader,
  PaperHeaderSkeleton,
  SignalHeading,
} from '../../(sidebar)/papers/[id]/paper-header'
import { DIMENSION_ROWS } from '../../(sidebar)/papers/[id]/skeletons'
import { RunFacts, RunFactsSkeleton } from '../../(sidebar)/runs/[id]/run-facts'
import { StepTimeline, StepTimelineSkeleton } from '../../(sidebar)/runs/[id]/step-timeline'
import { RunsTable, RunsTableSkeleton } from '../../(sidebar)/runs/runs-table'
import { HistoryRailDemo, PaperPickerDemo } from './gallery-clients'

/**
 * The skeleton gallery: every data shape next to its loading state, on fixture
 * data. Unlisted (not in the studio nav) but always on — it is the target of
 * `bun run skeleton:drift`, which measures each [data-pair]'s loaded and
 * skeleton panes and fails on drift, and of `bun run screenshots --routes
 * skeletons`. `?motion=static` freezes the scan sweep for both.
 *
 * Panes are stacked, not side by side, so both are measured at the same width.
 */

const edition = fixtureEditions[0]
// The gallery card should show the typical shape: an abstract long enough to
// hit the two-line clamp, like almost every real paper at desktop width. The
// contract fixture's abstract is one line, which is the exception, so the
// gallery extends it locally rather than editing the shared fixture.
const paper = {
  ...fixturePapers[0],
  abstract:
    'We study coordinated tool use in multi-agent language model systems, showing that a shared scratchpad and a lightweight arbitration protocol reduce redundant calls by 41% while preserving task success across three benchmark suites, and that the effect strengthens as the number of cooperating agents grows from two to eight.',
  // Likewise the first dimension's rationale: real ones run to a couple of
  // lines, which is what the paper skeleton reserves (DIMENSION_ROWS).
  dimensions: fixturePapers[0].dimensions.map((d, i) =>
    i === 0
      ? {
          ...d,
          rationale:
            'Squarely in the agentic-AI focus: the paper studies how cooperating language-model agents divide tool calls between them, measures the effect on redundant work and task success across three benchmark suites, and reports how the gain scales as more agents join — the exact question the workspace is scanning for.',
        }
      : d,
  ),
}
// Five rows so the list pair exercises the page-sized skeleton; ids only need
// to be unique keys.
const fivePapers = Array.from({ length: 5 }, (_, i) => ({
  ...paper,
  id: `${paper.id.slice(0, -1)}${i}`,
}))

// Studio is English-only; the shared components take a translator.
const t: T = (s) => s

// Three sessions on two days: the fixture pair plus a question long enough
// to wrap, so the rail pair exercises both a day break and the two-line title.
const sessions = [
  ...fixtureSessions,
  {
    ...fixtureSessions[1],
    id: '00000000-0000-4000-8000-000000000053',
    title:
      'Which of these results would survive a replication attempt with a smaller model and a tighter budget?',
    turns_count: 3,
    updated_at: '2026-08-26T10:05:00Z',
  },
]

const pickerEntries: PaletteEntry[] = fivePapers.map((p) => ({
  id: p.id,
  title: p.title,
  first_author: p.authors[0] ?? null,
  source: p.source,
  signal_score: p.signal_score,
  created_at: p.created_at,
}))

const browserEditions: BrowserEdition[] = fixtureEditions.map((e) => ({
  runId: e.run_id,
  workspaceId: e.workspace_id,
  domain: fixtureWorkspace.name,
  date: e.date,
  title: e.title,
  inBrief: e.in_brief,
  proseSource: e.in_brief_source,
  funnel: {
    screened: e.funnel.fetched,
    included: e.funnel.passed_screening,
    inBriefing: e.funnel.surfaced,
  },
  papers: e.papers.map((p) => ({ id: p.id, title: p.title, signal: p.signal_score })),
}))

function Pair({
  shape,
  title,
  status,
  loaded,
  skeleton,
}: {
  shape: string
  title: string
  status: string
  loaded: ReactNode
  skeleton: ReactNode
}) {
  return (
    <section data-pair={shape} className="space-y-4">
      <SectionLabel>{title}</SectionLabel>
      <div data-pane="loaded">{loaded}</div>
      <Skeleton.Region data-pane="skeleton" status={status}>
        {skeleton}
      </Skeleton.Region>
    </section>
  )
}

export default async function SkeletonsPage({
  searchParams,
}: {
  searchParams: Promise<{ motion?: string }>
}) {
  const { motion } = await searchParams
  return (
    <div data-motion={motion === 'static' ? 'static' : undefined} className="space-y-12">
      <PageHeader
        eyebrow="Studio"
        title="Skeletons"
        description="Every data shape next to its loading state, on fixture data. The scan sweep runs live here; ?motion=static freezes it for bun run skeleton:drift and the screenshot harness."
      />

      <Pair
        shape="paper-card"
        title="Paper card"
        status="Loading paper"
        loaded={<PaperCard paper={paper} />}
        skeleton={<PaperCardSkeleton />}
      />

      <Pair
        shape="stat-band-funnel"
        title="Stat band · funnel"
        status="Loading the funnel"
        loaded={
          <StatBand
            items={[
              { value: edition.funnel.fetched, label: 'Screened', sub: 'matched the focus fields' },
              {
                value: edition.funnel.passed_screening,
                label: 'Included',
                sub: 'cleared the signal bar',
              },
              { value: edition.funnel.surfaced, label: 'In the briefing', sub: 'listed below' },
            ]}
            flow
            className="lg:grid-cols-3!"
          />
        }
        skeleton={
          <StatBandSkeleton
            count={3}
            labels={['Screened', 'Included', 'In the briefing']}
            subs={['matched the focus fields', 'cleared the signal bar', 'listed below']}
            flow
            className="lg:grid-cols-3!"
          />
        }
      />

      <Pair
        shape="stat-band-spark"
        title="Stat band · sparkline + delta"
        status="Loading stats"
        loaded={
          <StatBand
            items={[
              { value: 128, label: 'Runs', delta: 12, spark: [3, 5, 4, 8, 6, 9] },
              { value: '4,210', label: 'Papers fetched', delta: -4, spark: [9, 7, 8, 5, 6, 4] },
              { value: 311, label: 'Passed screening', delta: 2, spark: [2, 4, 3, 6, 5, 7] },
              { value: '$92.40', label: 'Total spend', delta: 8, spark: [1, 3, 2, 5, 4, 6] },
            ]}
          />
        }
        skeleton={<StatBandSkeleton count={4} withDelta below="spark" />}
      />

      <Pair
        shape="stat-band-vertical"
        title="Stat band · vertical"
        status="Loading stats"
        loaded={
          <StatBand
            orientation="vertical"
            flow
            items={[
              { value: 12, label: 'Fetched', sub: 'from the sources' },
              { value: 5, label: 'Passed screening', sub: '42% of fetched' },
              { value: 1, label: 'In the briefing', sub: 'listed below' },
            ]}
          />
        }
        skeleton={
          <StatBandSkeleton
            count={3}
            orientation="vertical"
            flow
            labels={['Fetched', 'Passed screening', 'In the briefing']}
            subs={['from the sources', '42% of fetched', 'listed below']}
            digits={2}
          />
        }
      />

      <Pair
        shape="stat-tile"
        title="Stat tile"
        status="Loading stat"
        loaded={
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Papers fetched" value={12} delta={4} sub="vs. yesterday" />
            <StatTile label="Included" value={5} sub="cleared the signal bar" />
          </div>
        }
        skeleton={
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTileSkeleton digits={2} />
            <StatTileSkeleton digits={2} />
          </div>
        }
      />

      <Pair
        shape="answer-markdown"
        title="Answer prose"
        status="Loading the brief"
        loaded={<AnswerMarkdown text={edition.in_brief} className="max-w-3xl text-base" />}
        skeleton={<AnswerMarkdownSkeleton className="max-w-3xl text-base" paragraphs={[2]} />}
      />

      <Pair
        shape="run-papers"
        title="Run papers list"
        status="Loading the papers"
        loaded={<RunPapers papers={fivePapers} workspace={fixtureWorkspace} />}
        skeleton={<RunPapersSkeleton />}
      />

      <Pair
        shape="runs-table"
        title="Runs table"
        status="Loading the runs"
        loaded={<RunsTable runs={fixtureRuns} />}
        skeleton={<RunsTableSkeleton rows={fixtureRuns.length} />}
      />

      <Pair
        shape="run-facts"
        title="Run facts"
        status="Loading the run"
        loaded={<RunFacts run={fixtureRunDetail} />}
        skeleton={<RunFactsSkeleton />}
      />

      <Pair
        shape="step-timeline"
        title="Step timeline"
        status="Loading the steps"
        loaded={<StepTimeline steps={fixtureSteps} />}
        skeleton={<StepTimelineSkeleton steps={fixtureSteps.length} />}
      />

      <Pair
        shape="paper-header"
        title="Paper header"
        status="Loading the paper"
        loaded={<PaperHeader paper={paper} t={t} lang="en" />}
        skeleton={<PaperHeaderSkeleton />}
      />

      {/* Literal inputs: the fixture paper is not on the canonical formula, so
          ledgerInputs() would refuse it. TRL 4 keeps the bonus row dim. */}
      <Pair
        shape="signal-ledger"
        title="Signal ledger"
        status="Loading the paper"
        loaded={
          <Card>
            <SignalLedger
              inputs={{ trl: 4, fit: 92, novelty: 74 }}
              heading={<SignalHeading t={t} />}
            />
          </Card>
        }
        skeleton={
          <Card>
            <SignalLedgerSkeleton heading={<SignalHeading t={t} />} />
          </Card>
        }
      />

      <Pair
        shape="dimensions"
        title="Dimension rows"
        status="Loading the paper"
        loaded={
          <DimensionsFrame>
            {paper.dimensions.map((d) => (
              <ScoreRow
                key={d.key}
                label={d.name}
                value={d.value}
                max={d.max}
                raw={d.raw}
                rationale={d.rationale}
                evidence={d.evidence}
              />
            ))}
          </DimensionsFrame>
        }
        skeleton={
          <DimensionsFrame state="skeleton">
            {DIMENSION_ROWS.map((row, i) => (
              <ScoreRowSkeleton key={i} {...row} />
            ))}
          </DimensionsFrame>
        }
      />

      <Pair
        shape="history-rail"
        title="Ask · history rail"
        status="Loading the assistant"
        loaded={
          <div className="max-w-sm">
            <HistoryRailDemo threads={sessions} />
          </div>
        }
        skeleton={
          <div className="max-w-sm">
            <HistoryRailSkeleton groups={[1, 2]} lines={[1, 1, 2]} />
          </div>
        }
      />

      <Pair
        shape="paper-picker"
        title="Ask · paper picker"
        status="Loading the assistant"
        loaded={
          <div className="max-w-2xl">
            <PaperPickerDemo entries={pickerEntries} />
          </div>
        }
        skeleton={
          <div className="max-w-2xl">
            <PaperPickerSkeleton rows={pickerEntries.length} />
          </div>
        }
      />

      <Pair
        shape="edition-browser"
        title="Briefings reading room"
        status="Loading the briefings"
        loaded={<EditionBrowser editions={browserEditions} lang="en" />}
        skeleton={
          <EditionBrowserSkeleton
            editions={browserEditions.length}
            papers={browserEditions[0].papers.length}
            briefParagraphs={[2]}
          />
        }
      />

      <Pair
        shape="exclusions-table"
        title="Screening log table"
        status="Loading the screening log"
        loaded={<ExclusionsTable exclusions={edition.exclusions} t={t} />}
        skeleton={
          <ExclusionsTableSkeleton t={t} rows={edition.exclusions.length} shape={[[2, 1]]} />
        }
      />
    </div>
  )
}

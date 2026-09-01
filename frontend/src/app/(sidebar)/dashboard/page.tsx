import { AnswerMarkdown } from '@/components/answer-markdown'
import { Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { SectionAnchors } from '@/components/top-bar'
import { getSessionUser } from '@/lib/auth/session'
import type { Edition } from '@/lib/bff/briefings/schema'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { papers as papersService } from '@/lib/bff/papers/service'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { fmt, formatDate } from '@/lib/i18n'
import { getLang, getT } from '@/lib/i18n-server'
import { isPassed } from '@/lib/papers/map'
import { byValueDesc } from '@/lib/papers/select'
import type { ScoredPaper, WorkspaceSummary } from '@/lib/papers/types'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import Link from 'next/link'
import { RunPapers } from './run-papers'

export const dynamic = 'force-dynamic'

const anchors = [
  { id: 'today', label: 'Today in brief' },
  { id: 'the-papers', label: 'The papers' },
]

export default async function DashboardPage() {
  const [user, ws, t, lang] = await Promise.all([
    getSessionUser(),
    getCurrentWorkspace(),
    getT(),
    getLang(),
  ])
  const name = user?.name.split(' ')[0] || t('there')

  // The latest completed run in the workspace and the papers it surfaced:
  // the dashboard claims no more than the list below shows.
  let workspace: WorkspaceSummary | null = null
  let latest: PipelineRun | null = null
  let papers: ScoredPaper[] = []
  let editionToday: Edition | null = null
  if (ws) {
    const [runs, scored, editions] = await forPage(
      Promise.all([
        runsService.listAll(ws.id, 'completed'),
        papersService.listAll(ws.id),
        briefings.listAll(ws.id, lang),
      ]),
    )
    editionToday = editions[0] ?? null
    latest = runs[0] ?? null
    if (scored) {
      workspace = scored.workspace
      papers = latest
        ? scored.papers
            .filter((p) => p.pipeline_run_id === latest!.id && isPassed(p.screening_status))
            .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
        : []
    }
  }

  const runDate = latest ? formatDate(latest.completed_at ?? latest.run_date, lang) : null
  const funnel = [
    {
      value: latest?.total_papers_fetched ?? 0,
      label: t('Screened'),
      sub: t('matched the focus fields'),
    },
    {
      value: latest?.total_papers_passed_screening ?? 0,
      label: t('Included'),
      sub: t('cleared the signal bar'),
    },
    { value: papers.length, label: t('In the briefing'), sub: t('listed below') },
  ]

  return (
    <div className="space-y-10">
      <SectionAnchors anchors={anchors} />

      <PageHeader
        eyebrow={runDate ? fmt(t('Today · {date}'), { date: runDate }) : t('Today')}
        title={fmt(t('Good morning, {name}'), { name })}
        actions={
          workspace && (
            <span className="bg-accent inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-[11px] font-medium text-white">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-white/80" />
              {workspace.name}
            </span>
          )
        }
      />

      {/* ------------------------------ Today in brief ---------------------------- */}
      {/* The latest edition's brief (template-written until the backend's
          reporting step produces prose — flagged when so). */}
      <section id="today" className="scroll-mt-28">
        {/* Three stages, so override the band's default four columns. */}
        <StatBand items={funnel} flow className="lg:grid-cols-3!" />
        <div className="mt-8">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <SectionLabel size="sm">{t('Today in brief')}</SectionLabel>
            {editionToday && (
              <Link
                href={`/briefing/${editionToday.date}`}
                className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
              >
                {t('Open briefing →')}
              </Link>
            )}
          </div>
          {ws && editionToday ? (
            <AnswerMarkdown
              text={editionToday.in_brief}
              className="mt-4 max-w-3xl text-base text-pretty text-zinc-600 dark:text-zinc-300"
            />
          ) : (
            <p className="mt-4 max-w-3xl text-base leading-relaxed text-pretty text-zinc-600 dark:text-zinc-300">
              {!ws ? t('No workspace selected') : t('No completed runs yet.')}
            </p>
          )}
          {editionToday?.in_brief_source === 'template' && (
            <p className="mt-2 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
              {t('Assembled automatically from this run.')}
            </p>
          )}
        </div>
      </section>

      {/* -------------------------------- The papers ------------------------------ */}
      <section id="the-papers" className="scroll-mt-28">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel size="sm">{t('The papers')}</SectionLabel>
          <Link
            href="/papers"
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {t('All papers →')}
          </Link>
        </div>
        <div className="mt-5">
          {latest && workspace ? (
            <RunPapers papers={papers} workspace={workspace} />
          ) : (
            <Card>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {ws
                  ? t('Once a pipeline run completes in this workspace, its papers appear here.')
                  : t('You are not a member of any workspace yet. Ask an administrator for access.')}
              </p>
            </Card>
          )}
        </div>
      </section>
    </div>
  )
}

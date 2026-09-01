import { AnswerMarkdown } from '@/components/answer-markdown'
import { Card, StatBand } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { fmt, formatDate, type Lang, type T } from '@/lib/i18n'
import Link from 'next/link'
import { editionToday, funnelCopy, latestRun, runPapers } from './data'
import { RunPapers } from './run-papers'

/**
 * The dashboard's streamed sections: one async Server Component per Suspense
 * boundary, each awaiting only its own data (through `forPage`, so a 401
 * still lands on /auth/logout). Every section returns a single root element —
 * the page wraps each in a <ViewTransition> pair with its skeleton.
 */

export async function TodayEyebrow({ wsId, t, lang }: { wsId: string; t: T; lang: Lang }) {
  const latest = await forPage(latestRun(wsId))
  const runDate = latest ? formatDate(latest.completed_at ?? latest.run_date, lang) : null
  return <>{runDate ? fmt(t('Today · {date}'), { date: runDate }) : t('Today')}</>
}

export async function Funnel({ wsId, t }: { wsId: string; t: T }) {
  const { latest, papers } = await forPage(runPapers(wsId))
  const copy = funnelCopy(t)
  const funnel = [
    { value: latest?.total_papers_fetched ?? 0, ...copy[0] },
    { value: latest?.total_papers_passed_screening ?? 0, ...copy[1] },
    { value: papers.length, ...copy[2] },
  ]
  // Three stages, so override the band's default four columns.
  return <StatBand items={funnel} flow className="lg:grid-cols-3!" />
}

export async function BriefLink({ wsId, t, lang }: { wsId: string; t: T; lang: Lang }) {
  const edition = await forPage(editionToday(wsId, lang))
  if (!edition) return null
  return (
    <Link
      href={`/briefing/${edition.date}`}
      className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
    >
      {t('Open briefing →')}
    </Link>
  )
}

export async function Brief({ wsId, t, lang }: { wsId: string; t: T; lang: Lang }) {
  const edition = await forPage(editionToday(wsId, lang))
  if (!edition) {
    return (
      <p className="mt-4 max-w-3xl text-base leading-relaxed text-pretty text-zinc-600 dark:text-zinc-300">
        {t('No completed runs yet.')}
      </p>
    )
  }
  // The latest edition's brief (template-written until the backend's
  // reporting step produces prose — flagged when so).
  return (
    <div>
      <AnswerMarkdown
        text={edition.in_brief}
        className="mt-4 max-w-3xl text-base text-pretty text-zinc-600 dark:text-zinc-300"
      />
      {edition.in_brief_source === 'template' && (
        <p className="mt-2 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
          {t('Assembled automatically from this run.')}
        </p>
      )}
    </div>
  )
}

export async function Papers({ wsId, t }: { wsId: string; t: T }) {
  const { latest, workspace, papers } = await forPage(runPapers(wsId))
  if (!latest || !workspace) {
    return (
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('Once a pipeline run completes in this workspace, its papers appear here.')}
        </p>
      </Card>
    )
  }
  return <RunPapers papers={papers} workspace={workspace} />
}

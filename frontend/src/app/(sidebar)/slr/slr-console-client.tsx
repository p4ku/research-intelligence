'use client'

import { Button } from '@/components/button'
import { Select } from '@/components/select'
import type {
  SLRDispute,
  SLRPipelineRunItem,
  SLRPRISMAMetrics,
  SLRROBAssessment,
} from '@/lib/bff/slr/schema'
import clsx from 'clsx'
import { useMemo, useState } from 'react'
import { AgreementKpiBanner } from './agreement-kpi-banner'
import { ArbiterConsole } from './arbiter-console'
import { PrismaFlowDiagram } from './prisma-flow-diagram'
import { RobTrafficLightMatrix } from './rob-traffic-light-matrix'

interface SlrConsoleClientProps {
  initialRuns: SLRPipelineRunItem[]
  initialMetrics: SLRPRISMAMetrics | null
  initialRob: SLRROBAssessment[]
  initialDisputes: SLRDispute[]
  initialRunId: string | null
  initialTab?: 'prisma' | 'arbiter' | 'rob'
}

export function SlrConsoleClient({
  initialRuns,
  initialMetrics,
  initialRob,
  initialDisputes,
  initialRunId,
  initialTab,
}: SlrConsoleClientProps) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    initialRunId || (initialRuns.length > 0 ? initialRuns[0].id : null),
  )
  const [metrics, setMetrics] = useState<SLRPRISMAMetrics | null>(initialMetrics)
  const [robAssessments, setRobAssessments] = useState<SLRROBAssessment[]>(initialRob)
  const [disputes, setDisputes] = useState<SLRDispute[]>(initialDisputes)
  const [activeTab, setActiveTab] = useState<'prisma' | 'arbiter' | 'rob'>(initialTab || 'prisma')
  const [isLoading, setIsLoading] = useState<boolean>(false)

  const _selectedRun = initialRuns.find((r) => r.id === selectedRunId) || null
  const pendingDisputesCount = useMemo(
    () => disputes.filter((d) => d.status === 'pending').length,
    [disputes],
  )

  async function handleRunChange(newRunId: string) {
    setSelectedRunId(newRunId)
    setIsLoading(true)

    try {
      const [mRes, robRes] = await Promise.all([
        fetch(`/bff/slr/runs/${newRunId}/metrics`).then((r) => (r.ok ? r.json() : null)),
        fetch(`/bff/slr/runs/${newRunId}/rob`).then((r) => (r.ok ? r.json() : [])),
      ])
      setMetrics(mRes)
      setRobAssessments(robRes)
    } catch {
      // Keep existing data on fetch failure
    } finally {
      setIsLoading(false)
    }
  }

  function handleDisputeResolved(resolvedId: string, finalDecision: string) {
    setDisputes((prev) =>
      prev.map((d) =>
        d.id === resolvedId
          ? {
              ...d,
              status: 'resolved',
              final_decision: finalDecision as 'include' | 'exclude',
              resolved_at: new Date().toISOString(),
            }
          : d,
      ),
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header & Run Switcher Bar */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-xs sm:flex-row sm:items-center dark:border-zinc-800 dark:bg-zinc-900">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-zinc-950 dark:text-white">
              SLR Review &amp; Quality Console
            </h1>
            <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-bold text-blue-700 dark:bg-blue-400/10 dark:text-blue-300">
              PRISMA &bull; RoB 2 &bull; Arbiter
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            Systematic Literature Review analytics, inter-rater concordance, flow diagram &amp;
            dispute reconciliation.
          </p>
        </div>

        {/* Switcher & Actions */}
        <div className="flex flex-wrap items-center gap-3">
          {initialRuns.length > 0 && (
            <div className="min-w-64">
              <Select
                value={selectedRunId || ''}
                onChange={(e) => handleRunChange(e.target.value)}
                className="w-full text-xs font-semibold"
              >
                {initialRuns.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name || `Run ${r.id.slice(0, 8)}`} ({r.workspace_name})
                  </option>
                ))}
              </Select>
            </div>
          )}

          <Button
            href="/audit-queue"
            plain
            className="text-xs font-semibold text-zinc-700 dark:text-zinc-300"
          >
            ← Audit Queue
          </Button>

          <Button
            href={`/slr/studies${selectedRunId ? `?runId=${encodeURIComponent(selectedRunId)}` : ''}`}
            color="emerald"
            className="text-xs font-semibold"
          >
            Included Studies ({metrics?.studies_included_synthesis ?? 0}) →
          </Button>

          <Button href="/briefing" color="dark/zinc" className="text-xs font-semibold">
            View Briefing →
          </Button>
        </div>
      </div>

      {/* KPI Banner: Agreement & AI Calibration */}
      <AgreementKpiBanner metrics={metrics} />

      {/* Main Content Tabs */}
      <div className="space-y-4">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-zinc-200 pb-2 dark:border-zinc-800">
          <button
            type="button"
            onClick={() => setActiveTab('prisma')}
            className={clsx(
              'inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all',
              activeTab === 'prisma'
                ? 'bg-zinc-950 text-white shadow-xs dark:bg-white dark:text-zinc-950'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            <span>📊 PRISMA 2020 Flow</span>
            {metrics?.studies_included_synthesis ? (
              <span className="py-0.2 rounded-full bg-zinc-700/50 px-1.5 text-[10px] text-white dark:bg-zinc-300 dark:text-zinc-900">
                {metrics.studies_included_synthesis}
              </span>
            ) : null}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('arbiter')}
            className={clsx(
              'inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all',
              activeTab === 'arbiter'
                ? 'bg-zinc-950 text-white shadow-xs dark:bg-white dark:text-zinc-950'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            <span>⚖️ Arbiter Console</span>
            {pendingDisputesCount > 0 ? (
              <span className="py-0.2 rounded-full bg-amber-500 px-1.5 text-[10px] font-extrabold text-zinc-950">
                {pendingDisputesCount} pending
              </span>
            ) : (
              <span className="py-0.2 rounded-full bg-zinc-200 px-1.5 text-[10px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                {disputes.length}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('rob')}
            className={clsx(
              'inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all',
              activeTab === 'rob'
                ? 'bg-zinc-950 text-white shadow-xs dark:bg-white dark:text-zinc-950'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
            )}
          >
            <span>🚦 Risk of Bias Matrix (RoB 2)</span>
            {robAssessments.length > 0 && (
              <span className="py-0.2 rounded-full bg-zinc-700/50 px-1.5 text-[10px] text-white dark:bg-zinc-300 dark:text-zinc-900">
                {robAssessments.length} studies
              </span>
            )}
          </button>
        </div>

        {/* Tab Body */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <span className="animate-pulse text-xs font-semibold text-zinc-500">
              Loading SLR metrics &amp; appraisals…
            </span>
          </div>
        ) : (
          <>
            {activeTab === 'prisma' && (
              <PrismaFlowDiagram
                metrics={metrics}
                runId={selectedRunId}
                workspaceId={_selectedRun?.workspace_id}
                onSelectTab={setActiveTab}
              />
            )}
            {activeTab === 'arbiter' && (
              <ArbiterConsole disputes={disputes} onDisputeResolved={handleDisputeResolved} />
            )}
            {activeTab === 'rob' && <RobTrafficLightMatrix assessments={robAssessments} />}
          </>
        )}
      </div>
    </div>
  )
}

/**
 * The corpus version: a fingerprint of the run ledger. Papers and extractions
 * only change when a pipeline run writes them, so a snapshot of the corpus is
 * current exactly as long as this string is. Order-independent. A running
 * run moves the version at each stage boundary — screening writes the
 * counters, extraction and scoring write rows the counters never show —
 * and never between them, so a poll mid-stage changes nothing. Pure.
 */
import { createHash } from 'node:crypto'
import type { PipelineRun } from '../pipeline-runs/schema'

export function corpusVersion(runs: readonly PipelineRun[]): string {
  const tuples = runs
    .map(
      (run) =>
        `${run.id}|${run.status}|${run.current_stage ?? ''}|${run.completed_at ?? ''}|${run.total_papers_fetched}|${run.total_papers_passed_screening}`,
    )
    .sort()
  return createHash('sha256').update(tuples.join('\n')).digest('base64url').slice(0, 22)
}

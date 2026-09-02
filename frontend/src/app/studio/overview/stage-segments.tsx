/**
 * Eight labelled 3px segments, one per pipeline stage, plus the sentence
 * that says the same thing in words. The bar is decoration for sighted
 * readers; the sentence is the accessible name and is always rendered,
 * which is what keeps the strip honest below 480px where the labels hide.
 */
import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import { STAGES, type PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'
import { segmentTones, stageSentence, type SegmentTone } from './derive'
import { MONO } from './primitives'

const SHORT: Record<(typeof STAGES)[number], string> = {
  search: 'Search',
  download: 'Download',
  ocr: 'OCR',
  abstract_screening: 'Abstract',
  full_text_screening: 'Full text',
  extraction: 'Extract',
  signal_score: 'Score',
  reporting: 'Report',
}

const BAR: Record<SegmentTone, string> = {
  idle: 'bg-line-soft',
  done: 'bg-foreground/25',
  now: 'bg-accent',
  bad: 'bg-negative',
}

const LABEL: Record<SegmentTone, string> = {
  idle: 'text-muted-foreground',
  done: 'text-muted-foreground',
  now: 'text-accent-ink font-semibold',
  bad: 'text-negative font-semibold',
}

export function StageSegments({
  run,
  steps,
  now,
  bar = true,
  className,
}: {
  run: PipelineRun
  steps: ComponentRun[] | null
  now: string
  /** False for a completed run: the sentence alone. */
  bar?: boolean
  className?: string
}) {
  const tones = segmentTones(run, steps)
  const sentence = stageSentence(run, steps, now)
  return (
    <span className={clsx('block', className)}>
      {bar && (
        <span aria-hidden="true" className="grid max-w-[440px] grid-cols-8 gap-0.5">
          {STAGES.map((stage, i) => (
            <span key={stage} className="block min-w-0">
              <span className={clsx('block h-[3px]', BAR[tones[i]])} />
              <span
                className={clsx(
                  'mt-1 block truncate text-[10px] leading-tight max-[480px]:hidden',
                  LABEL[tones[i]],
                )}
              >
                {SHORT[stage]}
              </span>
            </span>
          ))}
        </span>
      )}
      <span className={clsx('text-muted-foreground mt-1.5 block text-xs break-words', MONO)}>
        {sentence}
      </span>
    </span>
  )
}

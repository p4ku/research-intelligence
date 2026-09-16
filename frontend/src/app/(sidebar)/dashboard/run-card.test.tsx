import type { InFlightRun } from '@/lib/bff/pipeline-runs/admission'
import { ALL_ON } from '@/lib/features'
import type { T } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { HomeGrid } from './home-ui'
import { runCardNote } from './run-card'
import { LedgerSkeletonRegion } from './skeletons'

const t: T = (s) => s

function run(name: string, over: Partial<InFlightRun> = {}): InFlightRun {
  return {
    id: '00000000-0000-4000-8000-000000000103',
    workspace_id: '00000000-0000-4000-8000-0000000000a1',
    workspace_name: name,
    status: 'running',
    period_start: null,
    period_end: null,
    lookback_days: 7,
    ...over,
  }
}

describe('runCardNote', () => {
  test('nothing in flight: the rule, in one sentence', () => {
    expect(runCardNote({ ok: true, count: 0 }, [], t)).toBe(
      'Up to 5 briefings can run at once per domain. A new one tops the list when it finishes.',
    )
  })

  test('runs in flight: counted, domains named, repeats folded', () => {
    const flying = [run('Hybrid Computing'), run('Hybrid Computing'), run('Retail Robotics')]
    expect(runCardNote({ ok: true, count: 2 }, flying, t)).toBe(
      '3 running: Hybrid Computing ×2, Retail Robotics',
    )
  })

  test('at the cap: the domain and the number', () => {
    const one = run('Hybrid Computing')
    expect(
      runCardNote(
        { ok: false, reason: 'cap', domain: 'Hybrid Computing', count: 5, run: one },
        [one],
        t,
      ),
    ).toBe('Hybrid Computing has 5 briefings in progress. Wait for one to finish.')
  })

  test('a twin window: the domain', () => {
    const one = run('Hybrid Computing')
    expect(
      runCardNote(
        { ok: false, reason: 'duplicate', domain: 'Hybrid Computing', count: 1, run: one },
        [one],
        t,
      ),
    ).toBe('Hybrid Computing is already running this window.')
  })
})

describe('HomeGrid and DashboardSkeleton role visibility', () => {
  test('HomeGrid renders ledger with basis-full when card is omitted for researcher', () => {
    const out = renderToStaticMarkup(<HomeGrid ledger={<div>Ledger Content</div>} />)
    expect(out).toContain('Ledger Content')
    expect(out).toContain('basis-full')
    expect(out).not.toContain('<aside')
  })

  test('HomeGrid renders card aside when card is provided for admin/manager', () => {
    const out = renderToStaticMarkup(
      <HomeGrid ledger={<div>Ledger Content</div>} card={<div>Run Card</div>} />,
    )
    expect(out).toContain('Ledger Content')
    expect(out).toContain('Run Card')
    expect(out).toContain('<aside')
  })

  test('LedgerSkeletonRegion omits RunCardSkeleton when showCard is false', () => {
    const out = renderToStaticMarkup(
      <LedgerSkeletonRegion t={t} features={ALL_ON} showCard={false} />,
    )
    expect(out).toContain('Recent briefings')
    expect(out).toContain('basis-full')
    expect(out).not.toContain('<aside')
  })

  test('LedgerSkeletonRegion includes RunCardSkeleton when showCard is true', () => {
    const out = renderToStaticMarkup(
      <LedgerSkeletonRegion t={t} features={ALL_ON} showCard={true} />,
    )
    expect(out).toContain('Recent briefings')
    expect(out).toContain('<aside')
  })
})

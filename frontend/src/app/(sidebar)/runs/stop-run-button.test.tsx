import { BffClientError } from '@/lib/bff/client'
import { problemBody } from '@/lib/bff/core/problem'
import type { RunStatus } from '@/lib/bff/pipeline-runs/schema'
import { makeT } from '@/lib/i18n'
import { de } from '@/locales/de'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { offersStop } from './run-presentation'
import { StopRunButton, StopRunView, stopErrorMessage } from './stop-run-button'

const run = { id: '4f6b1c1e-0d5b-4f8b-9d4b-2f8c6a9d1e10', workspace_name: 'Hybrid Computing' }

const view = (t = (s: string) => s, live = true) =>
  renderToStaticMarkup(
    <StopRunView
      run={run}
      t={t}
      live={live}
      open={false}
      stopping={false}
      error={null}
      onOpen={() => {}}
      onClose={() => {}}
      onConfirm={() => {}}
    />,
  )

describe('offersStop', () => {
  test('only a run still in flight can be stopped', () => {
    const expected: Record<RunStatus, boolean> = {
      pending: true,
      running: true,
      completed: false,
      failed: false,
      aborted: false,
    }
    for (const [status, offered] of Object.entries(expected)) {
      expect(offersStop(status as RunStatus)).toBe(offered)
    }
  })
})

describe('StopRunButton', () => {
  test('renders nothing for a run that has ended', () => {
    for (const status of ['completed', 'failed', 'aborted'] as const) {
      expect(renderToStaticMarkup(<StopRunButton run={{ ...run, status }} />)).toBe('')
    }
  })

  test('the trigger is a positioned button so a linked row does not take its click', () => {
    const out = view()
    expect(out).toContain('type="button"')
    expect(out).toMatch(/class="[^"]*\brelative\b/)
    expect(out).toContain('Stop')
    // A closed dialog renders no DOM: only the trigger is on the page.
    expect(out).not.toContain('alertdialog')
  })

  test('once the run has ended the trigger goes, whatever the dialog is doing', () => {
    expect(view(undefined, false)).toBe('')
  })

  test('reads in German', () => {
    expect(view(makeT('de'))).toContain('Stopp')
    for (const key of [
      'Stop this run?',
      'The {domain} run will stop where it is. This cannot be undone.',
      'Stopping…',
      'This run has already ended.',
      'Only an admin or manager of this domain can stop its runs.',
      "Couldn't stop this run. Try again.",
    ]) {
      expect(de[key]).toBeDefined()
    }
  })
})

describe('stopErrorMessage', () => {
  const t = (s: string) => s
  const failure = (slug: Parameters<typeof problemBody>[0]) =>
    new BffClientError(problemBody(slug, { detail: 'Error: raw Django prose.' }))

  test('names the two refusals the backend makes', () => {
    expect(stopErrorMessage(failure('conflict'), t)).toBe('This run has already ended.')
    expect(stopErrorMessage(failure('forbidden'), t)).toBe(
      'Only an admin or manager of this domain can stop its runs.',
    )
  })

  test('never prints Django prose, and has a sentence for a dead network', () => {
    expect(stopErrorMessage(failure('upstream-error'), t)).not.toContain('Django')
    expect(stopErrorMessage(new TypeError('Failed to fetch'), t)).toBe(
      "Couldn't stop this run. Try again.",
    )
  })
})

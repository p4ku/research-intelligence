import { describe, expect, test } from 'bun:test'
import { editionHref, screeningLogPdfHref } from './href'

const WS = '00000000-0000-4000-8000-000000000001'
const RUN = '00000000-0000-4000-8000-000000000101'

describe('editionHref', () => {
  test('the day alone — what a link from before domains and runs were in the URL means', () => {
    expect(editionHref('2026-08-31', undefined)).toBe('/briefing/2026-08-31')
    expect(editionHref('2026-08-31', undefined, {})).toBe('/briefing/2026-08-31')
  })

  test('the domain, then the run — every link the app mints carries both', () => {
    expect(editionHref('2026-08-31', WS)).toBe(`/briefing/2026-08-31?domain=${WS}`)
    expect(editionHref('2026-08-31', WS, { runId: RUN })).toBe(
      `/briefing/2026-08-31?domain=${WS}&run=${RUN}`,
    )
  })

  test('a run without a domain is kept — a crumb built from a trimmed URL keeps what it has', () => {
    expect(editionHref('2026-08-31', undefined, { runId: RUN })).toBe(
      `/briefing/2026-08-31?run=${RUN}`,
    )
  })

  test('the screening log sits under the edition with the same query', () => {
    expect(editionHref('2026-08-31', WS, { runId: RUN, sub: 'run' })).toBe(
      `/briefing/2026-08-31/run?domain=${WS}&run=${RUN}`,
    )
    expect(editionHref('2026-08-31', undefined, { sub: 'run' })).toBe('/briefing/2026-08-31/run')
  })
})

describe('screeningLogPdfHref', () => {
  test('the BFF export for the same edition, in the BFF query names', () => {
    expect(screeningLogPdfHref('2026-08-31')).toBe('/bff/briefings/2026-08-31/screening-log')
    expect(screeningLogPdfHref('2026-08-31', WS, RUN)).toBe(
      `/bff/briefings/2026-08-31/screening-log?workspace_id=${WS}&run_id=${RUN}`,
    )
    expect(screeningLogPdfHref('2026-08-31', undefined, RUN)).toBe(
      `/bff/briefings/2026-08-31/screening-log?run_id=${RUN}`,
    )
  })
})

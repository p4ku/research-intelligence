import { COMPONENT_LABELS, STEP_LABELS } from '@/lib/bff/component-runs/normalise'
import type { ComponentSummary } from '@/lib/bff/component-runs/schema'
import { STAGE_LABELS } from '@/lib/bff/pipeline-runs/schema'
import { makeT } from '@/lib/i18n'
import { de } from '@/locales/de'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  formatDuration,
  formatTokens,
  formatUsd,
  runStatusLabel,
  StepSummary,
} from './run-presentation'
import { COLUMNS } from './runs-table'

describe('formatDuration', () => {
  test('sub-second, seconds, minutes and hours', () => {
    expect(formatDuration(0.08)).toBe('0.08s')
    expect(formatDuration(0.84)).toBe('0.84s')
    expect(formatDuration(43.0)).toBe('43.0s')
    expect(formatDuration(68)).toBe('1m 08s')
    expect(formatDuration(233)).toBe('3m 53s')
    expect(formatDuration(3600)).toBe('1h 00m')
    // The zombie watchdog's 120-minute pipeline ceiling must not read "120m".
    expect(formatDuration(7200)).toBe('2h 00m')
    expect(formatDuration(7261)).toBe('2h 01m')
  })

  test('never emits a 60-second remainder', () => {
    // `duration_seconds` is a 6-decimal float, so remainders land arbitrarily
    // close to a minute boundary. Rounding the remainder on its own yields
    // "1m 60s"; rounding to whole seconds before splitting cannot.
    expect(formatDuration(119.5)).toBe('2m 00s')
    expect(formatDuration(119.7)).toBe('2m 00s')
    expect(formatDuration(3599.7)).toBe('1h 00m')
    for (let s = 59; s < 7200; s += 0.1) {
      expect(formatDuration(s)).not.toContain(' 60s')
    }
  })

  test('the seconds/minutes boundary does not print 60.0s', () => {
    expect(formatDuration(59.9)).toBe('59.9s')
    expect(formatDuration(59.96)).toBe('1m 00s')
  })

  test('null, non-finite and negative all render as an em dash', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(Number.NaN)).toBe('—')
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe('—')
    expect(formatDuration(-5)).toBe('—')
  })
})

describe('formatUsd', () => {
  test('precision follows magnitude', () => {
    expect(formatUsd(0.0029)).toBe('$0.0029')
    expect(formatUsd(0.05)).toBe('$0.05')
    expect(formatUsd(1.2269)).toBe('$1.23')
  })

  test('unmeasured is an em dash, measured zero is $0', () => {
    // Five of the seven step types record no cost at all. That must not read
    // as a measurement of zero.
    expect(formatUsd(null)).toBe('—')
    expect(formatUsd(0)).toBe('$0')
  })

  test('negatives keep the sign outside the currency symbol', () => {
    // The unattributed-spend figure is signed: steps can book more than the
    // run total. "$-0.0500" is not a currency amount.
    expect(formatUsd(-0.05)).toBe('-$0.05')
    expect(formatUsd(-0.0004)).toBe('-$0.0004')
    expect(formatUsd(-1.5)).toBe('-$1.50')
  })
})

describe('formatTokens', () => {
  test('groups digits, and null is an em dash', () => {
    expect(formatTokens(1492568)).toBe('1,492,568')
    expect(formatTokens(0)).toBe('0')
    expect(formatTokens(null)).toBe('—')
  })
})

/* --------------------------------- German --------------------------------- */

// U+202F, the narrow no-break space the terminology sheet puts before a unit,
// a percent sign and the currency symbol. Escaped so a plain space cannot
// creep in unnoticed.
const NNBSP = '\u202f'

describe('German readings', () => {
  test('durations take the decimal comma and the DIN abbreviations', () => {
    expect(formatDuration(0.84, 'de')).toBe(`0,84${NNBSP}s`)
    expect(formatDuration(43.0, 'de')).toBe(`43,0${NNBSP}s`)
    expect(formatDuration(68, 'de')).toBe(`1${NNBSP}Min. 08${NNBSP}s`)
    expect(formatDuration(7440, 'de')).toBe(`2${NNBSP}Std. 04${NNBSP}Min.`)
    expect(formatDuration(null, 'de')).toBe('—')
  })

  test('spend puts the symbol after the amount, English before it', () => {
    expect(formatUsd(12.34, 'de')).toBe(`12,34${NNBSP}$`)
    expect(formatUsd(0, 'de')).toBe(`0${NNBSP}$`)
    // formatNumber groups, so the English form carries its thousands comma.
    expect(formatUsd(1234.5, 'en')).toBe('$1,234.50')
    expect(formatUsd(1234.5, 'de')).toBe(`1.234,50${NNBSP}$`)
  })

  test('the status word is translated, not the wire value capitalised', () => {
    const t = makeT('de')
    expect(runStatusLabel('aborted', t)).toBe('Abgebrochen')
    expect(runStatusLabel('completed', t)).toBe('Abgeschlossen')
    expect(runStatusLabel('running', t)).toBe('Läuft')
  })
})

/* ------------------------------- Step summary ------------------------------- */

describe('StepSummary', () => {
  // A hookless server component, so the test calls it and renders what it
  // returns rather than reaching for JSX in a .ts file.
  const markup = (summary: ComponentSummary) => renderToStaticMarkup(StepSummary({ summary }))

  test('the scoring step reads its average and best as whole scores', () => {
    // The Schwarz Score is a whole number wherever it is shown; a one-decimal
    // "88.5" here would disagree with the paper card and the briefing.
    const html = markup({ kind: 'signal_score', scored: 8, total: 10, avg: 71.25, max: 88.5 })
    expect(html).toContain('>71<')
    expect(html).toContain('>89<')
    expect(html).not.toContain('71.3')
    expect(html).not.toContain('88.5')
  })

  test('an unscored step shows no figures at all', () => {
    const html = markup({ kind: 'signal_score', scored: 0, total: 10, avg: null, max: null })
    expect(html).not.toContain('avg')
    expect(html).not.toContain('max')
  })

  test('download step clearly displays downloaded, cached (even when 0), and failed counts', () => {
    const htmlWithZeroCache = markup({ kind: 'download', downloaded: 23, cached: 0, failed: 38 })
    expect(htmlWithZeroCache).toContain('>23<')
    expect(htmlWithZeroCache).toContain('downloaded')
    expect(htmlWithZeroCache).toContain('>0<')
    expect(htmlWithZeroCache).toContain('cached')
    expect(htmlWithZeroCache).toContain('>38<')
    expect(htmlWithZeroCache).toContain('failed')

    const htmlAllCached = markup({ kind: 'download', downloaded: 0, cached: 3, failed: 3 })
    expect(htmlAllCached).toContain('>0<')
    expect(htmlAllCached).toContain('downloaded')
    expect(htmlAllCached).toContain('>3<')
    expect(htmlAllCached).toContain('cached')
    expect(htmlAllCached).toContain('>3<')
    expect(htmlAllCached).toContain('failed')
  })
})

/* ---------------------------- Dynamic-label guard --------------------------- */

/**
 * Three tables of English copy reach `t()` through a variable — step titles
 * (component-runs/normalise.ts), the runs table's column headers, and the
 * pipeline stage names (pipeline-runs/schema.ts). The static audit in
 * lib/i18n.test.ts only sees literal `t('…')` calls, so it cannot catch a
 * label added here without its German. These do. Same shape as the registry
 * guard in lib/features.test.ts.
 */
describe('dynamically translated labels', () => {
  test('every step title has a German translation', () => {
    const labels = [...Object.values(STEP_LABELS), ...Object.values(COMPONENT_LABELS)]
    expect(labels.filter((label) => !(label in de))).toEqual([])
  })

  test('every runs-table column header has a German translation', () => {
    expect(COLUMNS.map((c) => c.label).filter((label) => !(label in de))).toEqual([])
  })

  test('every known pipeline stage has a German translation', () => {
    expect(Object.values(STAGE_LABELS).filter((label) => !(label in de))).toEqual([])
  })
})

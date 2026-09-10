import { RadarChart, wrapAxisLabel } from '@/components/charts'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

// The seven-dimension profile from the paper rail: two names long enough to
// have overlapped their neighbours before the labels learned to wrap.
const AXES = [
  { label: 'TRL', value: 40 },
  { label: 'Rigour', value: 70 },
  { label: 'Significance', value: 88 },
  { label: 'Schwarz Fit', value: 45 },
  { label: 'Hardware & Interconnect Technology', value: 55 },
  { label: 'Novelty', value: 82 },
  { label: 'Sovereign Cloud & Commercial Viability', value: 74 },
]

describe('wrapAxisLabel', () => {
  test('breaks on words within the budget', () => {
    expect(wrapAxisLabel('Sovereign Cloud & Commercial Viability', 12, 4)).toEqual([
      'Sovereign',
      'Cloud &',
      'Commercial',
      'Viability',
    ])
  })

  test('leaves a label that fits on one line', () => {
    expect(wrapAxisLabel('Significance', 14)).toEqual(['Significance'])
  })

  test('hyphenates a word no line can hold', () => {
    expect(wrapAxisLabel('Interoperabilitätsanforderungen', 10, 2)).toEqual([
      'Interoper-',
      'abilitäts…',
    ])
  })

  test('ellipses only what runs past the last line', () => {
    const lines = wrapAxisLabel('one two three four five six seven', 9, 2)
    expect(lines).toHaveLength(2)
    expect(lines[1]!.endsWith('…')).toBe(true)
  })
})

describe('RadarChart', () => {
  const out = renderToStaticMarkup(<RadarChart axes={AXES} size={260} />)

  test('scales to its box rather than spilling out of the card', () => {
    expect(out).toContain('viewBox="0 0 260 198"')
    expect(out).toContain('h-auto w-full')
    expect(out).not.toContain('overflow-visible')
  })

  test('anchors each label away from the plot', () => {
    // Top and bottom centred, the sides pushed outward.
    expect(out).toContain('text-anchor="middle"')
    expect(out).toContain('text-anchor="start"')
    expect(out).toContain('text-anchor="end"')
  })

  test('stacks a long name over several lines', () => {
    expect(out).toContain('<tspan x="101.79755695735872" dy="0">Hardware &amp;</tspan>')
    expect(out).toContain('<tspan x="101.79755695735872" dy="11">Interconnect</tspan>')
    expect(out).toContain('<tspan x="101.79755695735872" dy="11">Technology</tspan>')
    // No line runs on past the label gutter.
    const lines = [...out.matchAll(/<tspan[^>]*>([^<]*)<\/tspan>/g)].map((m) =>
      m[1]!.replaceAll('&amp;', '&'),
    )
    expect(Math.max(...lines.map((l) => l.length))).toBeLessThanOrEqual(13)
  })

  test('keeps a name whole when the flank has the room', () => {
    expect(out).toContain('>Sovereign</tspan>')
    expect(out).toContain('>Viability</tspan>')
    expect(out).not.toContain('<title>')
  })

  test('keeps the full name in a title wherever it was clipped', () => {
    const tight = renderToStaticMarkup(<RadarChart axes={AXES} size={180} />)
    expect(tight).toContain('<title>Sovereign Cloud &amp; Commercial Viability</title>')
    // A label that fits whole needs no tooltip.
    expect(tight).not.toContain('<title>Novelty</title>')
  })

  test('reads out the profile for assistive tech', () => {
    expect(out).toContain('role="img"')
    expect(out).toContain('Significance 88')
  })

  // The accessible name used to round the 0–100 value itself, so a TRL axis
  // read "TRL 40" out loud while the chart printed "4", and a 74.6 fit was
  // announced twice over. It now quotes the labels the chart draws.
  test('reads out exactly the figures the chart prints', () => {
    const axes = [
      { label: 'TRL', value: 40, shown: '4' },
      { label: 'Rigour', value: 74.6 },
      { label: 'Novelty', value: 82 },
    ]
    const html = renderToStaticMarkup(<RadarChart axes={axes} size={260} valueLabels />)
    expect(html).toContain('aria-label="TRL 4, Rigour 75, Novelty 82"')
    for (const shown of ['4', '75', '82']) {
      expect(html).toContain(`tabular-nums dark:fill-white">${shown}</tspan>`)
    }
  })
})

import { fixturePapers } from '@/lib/bff/papers/fixtures'
import { ALL_ON } from '@/lib/features'
import { FeaturesTestProvider } from '@/lib/features-client'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PaperCard, PaperCardSkeleton } from './paper-card'

// The card chrome, pinned: a Frame refactor must not change the loaded look.
const CARD_CLASSES =
  'flex items-start gap-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-950/10 dark:bg-zinc-900 dark:ring-white/10'

describe('PaperCard', () => {
  const paper = fixturePapers[0]
  const out = renderToStaticMarkup(<PaperCard paper={paper} />)

  test('loaded card keeps its exact chrome, link and clamp', () => {
    expect(out).toContain(CARD_CLASSES)
    expect(out).toContain('group-hover:-translate-y-px')
    expect(out).toContain('data-shape="paper-card"')
    expect(out).toContain('data-state="loaded"')
    expect(out).toContain(`href="/papers/${paper.id}"`)
    expect(out).toContain('line-clamp-2')
    expect(out).toContain(paper.title)
  })

  test('carries the star beside the link, never inside it', () => {
    expect(out).toContain('aria-label="Star this paper"')
    expect(out).toContain('aria-pressed="false"')
    // The button closes after the link: a sibling in the group wrapper.
    expect(out.indexOf('</a>')).toBeLessThan(out.indexOf('aria-label="Star this paper"'))
  })

  test('drops the star when the provider says the stars flag is off', () => {
    // The sibling of the case above: with no provider every flag reads ON, so
    // this is the only render that proves the gate is wired to the flag and
    // not to something else. The link and its chrome are untouched.
    const off = renderToStaticMarkup(
      <FeaturesTestProvider features={{ ...ALL_ON, stars: false }}>
        <PaperCard paper={paper} />
      </FeaturesTestProvider>,
    )
    expect(off).not.toContain('aria-label="Star this paper"')
    expect(off).not.toContain('aria-pressed')
    expect(off).toContain(`href="/papers/${paper.id}"`)
  })

  test('strip reads Schwarz Fit, the next dimension, then the TRL chip', () => {
    // The fixture's definitions are ordered fit, novelty, TRL already; the
    // second render ranks the fit last to prove it still leads the strip.
    const order = (html: string) =>
      ['Fit score', 'Novelty Score', 'TRL 4'].map((s) => html.indexOf(s))
    expect(order(out).every((i) => i >= 0)).toBe(true)
    expect(order(out)).toEqual([...order(out)].sort((a, b) => a - b))

    const fitLast = {
      ...paper,
      dimensions: paper.dimensions!.map((d) => ({
        ...d,
        order: d.name === 'Fit Score' ? 9 : d.name === 'Novelty Score' ? 1 : 2,
      })),
    }
    const reranked = renderToStaticMarkup(<PaperCard paper={fitLast} />)
    expect(order(reranked).every((i) => i >= 0)).toBe(true)
    expect(order(reranked)).toEqual([...order(reranked)].sort((a, b) => a - b))
  })

  // One rounding rule (10 Sep 2026): the strip and the ring print whole
  // numbers, and the ring's colour still reads the exact stored value.
  test('rounds a long float in the strip to a whole number', () => {
    const messy = {
      ...paper,
      dimensions: paper.dimensions!.map((d) =>
        d.key === 'fit_score' ? { ...d, value: 61.666666666666664, raw: '61.666666666666664' } : d,
      ),
    }
    const html = renderToStaticMarkup(<PaperCard paper={messy} />)
    expect(html).toContain('>62</span>')
    expect(html).not.toContain('61.66')
  })

  test('a score just under the band prints rounded up but keeps the warn colour', () => {
    const html = renderToStaticMarkup(<PaperCard paper={{ ...paper, signal_score: 74.6 }} />)
    expect(html).toContain('>75</span>')
    expect(html).toContain('stroke="var(--warn)"')
    expect(html).not.toContain('stroke="var(--accent)"')
  })

  test('an unscored paper reads as a dash, not a number', () => {
    const html = renderToStaticMarkup(<PaperCard paper={{ ...paper, signal_score: null }} />)
    expect(html).toContain('>—</span>')
    expect(html).toContain('Unscored')
  })

  test('the ceiling prints whole', () => {
    const html = renderToStaticMarkup(<PaperCard paper={{ ...paper, signal_score: 100 }} />)
    expect(html).toContain('>100</span>')
    expect(html).toContain('stroke="var(--accent)"')
  })

  test('names the domain in the meta row only when given one', () => {
    expect(out).not.toContain('Hybrid Computing')
    const withDomain = renderToStaticMarkup(<PaperCard paper={paper} domain="Hybrid Computing" />)
    expect(withDomain).toContain('Hybrid Computing')
  })
})

describe('PaperCardSkeleton', () => {
  const out = renderToStaticMarkup(<PaperCardSkeleton />)

  test('same frame — but no link, no star, no hover affordances, no clamp, no pulse', () => {
    expect(out).toContain(CARD_CLASSES)
    expect(out).toContain('data-state="skeleton"')
    expect(out).not.toContain('href=')
    expect(out).not.toContain('aria-pressed')
    expect(out).not.toContain('line-clamp-2')
    expect(out).not.toContain('hover:')
    expect(out).not.toContain('animate-pulse')
  })

  test('exposes the same measurable rows as the loaded card', () => {
    for (const row of ['meta', 'title', 'abstract', 'footer']) {
      expect(out).toContain(`data-row="${row}"`)
    }
  })
})

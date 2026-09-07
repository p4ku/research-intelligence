import { fixturePapers } from '@/lib/bff/papers/fixtures'
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
    expect(out).toContain('hover:-translate-y-px')
    expect(out).toContain('data-shape="paper-card"')
    expect(out).toContain('data-state="loaded"')
    expect(out).toContain(`href="/papers/${paper.id}"`)
    expect(out).toContain('line-clamp-2')
    expect(out).toContain(paper.title)
  })

  test('names the domain in the meta row only when given one', () => {
    expect(out).not.toContain('Hybrid Computing')
    const withDomain = renderToStaticMarkup(<PaperCard paper={paper} domain="Hybrid Computing" />)
    expect(withDomain).toContain('Hybrid Computing')
  })
})

describe('PaperCardSkeleton', () => {
  const out = renderToStaticMarkup(<PaperCardSkeleton />)

  test('same frame — but no link, no hover affordances, no clamp, no pulse', () => {
    expect(out).toContain(CARD_CLASSES)
    expect(out).toContain('data-state="skeleton"')
    expect(out).not.toContain('href=')
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

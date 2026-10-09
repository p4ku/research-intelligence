import { ALL_ON } from '@/lib/features'
import { makeT } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PaperNav, PaperNavSkeleton, type PaperNeighbours } from './paper-nav'

const t = makeT('en')

describe('PaperNav Component Rendering', () => {
  test('renders navigation with active prev and next links and position indicator', () => {
    const neighbours: PaperNeighbours = {
      prev: '/papers/paper-1',
      next: '/papers/paper-3',
      position: 2,
      total: 10,
    }

    const html = renderToStaticMarkup(
      <PaperNav neighbours={neighbours} t={t} lang="en" features={ALL_ON} />,
    )

    expect(html).toContain('data-shape="paper-nav"')
    expect(html).toContain('href="/papers/paper-1"')
    expect(html).toContain('href="/papers/paper-3"')
    expect(html).toContain('2 of 10')
    expect(html).toContain('All papers')
  })

  test('renders disabled arrows and dash when neighbours is null', () => {
    const html = renderToStaticMarkup(
      <PaperNav neighbours={null} t={t} lang="en" features={ALL_ON} />,
    )

    expect(html).toContain('data-shape="paper-nav"')
    expect(html).not.toContain('href="/papers/paper')
    expect(html).toContain('—')
    expect(html).toContain('All papers')
  })

  test('disables previous arrow for the first paper and enables next arrow', () => {
    const neighbours: PaperNeighbours = {
      prev: null,
      next: '/papers/paper-2',
      position: 1,
      total: 5,
    }

    const html = renderToStaticMarkup(
      <PaperNav neighbours={neighbours} t={t} lang="en" features={ALL_ON} />,
    )

    expect(html).toContain('href="/papers/paper-2"')
    expect(html).toContain('1 of 5')
    // Previous paper arrow should be disabled span, not a link
    expect(html).not.toContain('href="null"')
  })

  test('renders custom exit back link when provided', () => {
    const customExit = {
      href: '/briefing/2026-10-09',
      label: 'Back to briefing',
    }

    const html = renderToStaticMarkup(
      <PaperNav neighbours={null} t={t} lang="en" features={ALL_ON} back={customExit} />,
    )

    expect(html).toContain('href="/briefing/2026-10-09"')
    expect(html).toContain('Back to briefing')
  })

  test('PaperNavSkeleton renders matching frame and skeleton elements', () => {
    const html = renderToStaticMarkup(<PaperNavSkeleton t={t} features={ALL_ON} />)

    expect(html).toContain('data-shape="paper-nav"')
    expect(html).toContain('data-state="skeleton"')
    expect(html).toContain('All papers')
    expect(html).toContain('bg-foreground/8')
  })
})

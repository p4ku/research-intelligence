import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PageNav } from './page-nav'

describe('PageNav Component', () => {
  test('returns null when pageCount is 1 or less', () => {
    const out = renderToStaticMarkup(<PageNav page={1} pageCount={1} onChange={() => {}} />)
    expect(out).toBe('')
  })

  test('renders pagination with page numbers and Prev/Next buttons', () => {
    const out = renderToStaticMarkup(<PageNav page={3} pageCount={8} onChange={() => {}} />)
    expect(out).toContain('aria-label="Pagination"')
    expect(out).toContain('aria-current="page"')
    expect(out).toContain('Previous')
    expect(out).toContain('Next')
    expect(out).toContain('>3<')
    expect(out).toContain('>4<')
    expect(out).toContain('>8<')
  })

  test('displays loading indicator when pendingPage is active', () => {
    const out = renderToStaticMarkup(
      <PageNav page={3} pageCount={8} onChange={() => {}} pendingPage={4} disabled={true} />,
    )
    expect(out).toContain('aria-busy="true"')
    // Target page 4 has animate-pulse, loading spinner, and aria-busy
    expect(out).toContain('animate-pulse')
    expect(out).toContain('disabled=""')
    expect(out).toContain('role="status"')
    expect(out).toContain('aria-label="Loading"')
  })

  test('displays spinner on Next button when pendingPage is next page', () => {
    const out = renderToStaticMarkup(
      <PageNav page={3} pageCount={8} onChange={() => {}} pendingPage={4} />,
    )
    // Next button has isNextLoading active
    expect(out).toContain('text-accent')
    expect(out).toContain('aria-busy="true"')
  })

  test('displays spinner on Previous button when pendingPage is previous page', () => {
    const out = renderToStaticMarkup(
      <PageNav page={3} pageCount={8} onChange={() => {}} pendingPage={2} />,
    )
    // Previous button has isPrevLoading active
    expect(out).toContain('text-accent')
    expect(out).toContain('aria-busy="true"')
  })
})

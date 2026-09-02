import { describe, expect, test } from 'bun:test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { RouteError } from './route-error'

const err = (digest?: string) => Object.assign(new Error('kaboom'), { digest })

const html = (digest?: string) =>
  renderToStaticMarkup(
    <RouteError
      error={err(digest)}
      retry={() => {}}
      scope="test"
      heading="Couldn't load this page."
      description="Nothing was lost."
      back={{ href: '/dashboard', label: 'Back to Today' }}
    />,
  )

describe('RouteError', () => {
  test('shows the digest as a reference, never the raw message', () => {
    const out = html('abc123')
    expect(out).toContain('abc123')
    expect(out).not.toContain('kaboom')
  })

  test('omits the reference line when there is no digest', () => {
    const out = html()
    expect(out).not.toContain('Reference')
    expect(out).not.toContain('undefined')
  })

  test('is announced and offers a retry plus an escape route', () => {
    const out = html('abc123')
    expect(out).toContain('role="alert"')
    expect(out).toContain('Retry')
    expect(out).toContain('href="/dashboard"')
  })
})

// Offense #7: error ink must clear WCAG 1.4.3 on the shipped ground. Reads the
// live tokens so a palette tweak cannot quietly drop error text below the
// floor again — and documents why `text-warn` is a fill, never a text colour.
describe('error ink contrast', () => {
  const lum = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    const f = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }
  const ratio = (a: string, b: string) => {
    const [hi, lo] = [lum(a), lum(b)].sort((m, n) => n - m)
    return (hi + 0.05) / (lo + 0.05)
  }

  test('--negative clears 4.5:1 on white; --warn does not', () => {
    const css = readFileSync(join(import.meta.dir, '../styles/tailwind.css'), 'utf8')
    const negative = css.match(/--negative:\s*(#[0-9a-f]{6})/)?.[1]
    const warn = css.match(/--warn:\s*(#[0-9a-f]{6})/)?.[1]
    expect(negative).toBeDefined()
    expect(warn).toBeDefined()
    expect(ratio(negative!, '#ffffff')).toBeGreaterThanOrEqual(4.5)
    expect(ratio(warn!, '#ffffff')).toBeLessThan(4.5)
  })
})
